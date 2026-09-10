"""统一日志配置（Phase 0.2 / B2；2026-09-10 增加「落盘 + 崩溃取证」）。

背景（为什么要有文件日志）：
    原先只输出到控制台——**服务挂掉后终端窗口一关，证据就没了**。
    2026-09-10 实测：后端 8000 出现「运行着运行着就挂了」，事后完全无法追溯
    （项目内那几个 .log 全是 8 月的旧文件）。故补上落盘。

落盘位置：`backend/logs/`（可用环境变量 NA_LOG_DIR 覆盖目录、NA_LOG_FILE 覆盖主文件名）
    - backend.log  INFO+   （全量；5MB × 5 轮转）
    - error.log    WARNING+（只看异常/降级；排查时**先看这个**）

★ 判读方法（本次改造的核心价值）：
    - 有「进程启动」但**没有**「进程退出」 → 被**强杀**（taskkill /F / 任务管理器 / 关机）或硬崩溃；
    - 「启动 / 退出」成对出现            → **优雅退出**（Ctrl+C / uvicorn 正常关闭）；
    - 出现 CRITICAL「已捕获未处理异常」   → Python 层异常导致退出，**附完整 traceback**；
    - 出现 CRITICAL 且带 thread=…        → 某个后台线程炸了（本项目大量用后台线程，重点看）；
    - 看 `[heartbeat]` 的最后一条         → **进程确切死亡时间**与当时内存占用（内存持续上涨 = 泄漏）。

用法：
    from app.core.logging_config import get_logger
    logger = logging.getLogger(__name__)   # 亦可，setup 已在 import 时完成
    logger.info("...")
    logger.warning("...")   # 失败/异常/降级

约定：
- **保留控制台输出**（本机单人工具，看终端是主要排查方式），但不是简单替换 print：
  加了级别 + 时间 + 模块名，可用 NA_LOG_LEVEL 控制；
- uvicorn 自己的 logger（uvicorn / uvicorn.error / uvicorn.access）默认 propagate=False
  且自带 handler，**不会流到 root**，故需显式挂文件 handler（见 attach_uvicorn_file_logging）；
- 第三方库的噪声压到 WARNING。

⚠️ 关于本文件里的 `except Exception`（Phase 3.5 的静默禁令在**本文件豁免**）：
    日志基础设施自身的容错分支**不能调用 logging**——handler 还没建好时再记日志会二次失败，
    异常 hook 里再记日志可能递归，进程退出阶段 handler 可能已 shutdown。
    故本文件的 except 一律「吞掉并返回安全默认值」，且每处都有注释说明意图。
    豁免登记在 `tests/unit/test_except_logging.py` 的 `_EXEMPT_FILES`。**其他模块不适用该豁免。**
"""
import atexit
import logging
import logging.handlers
import os
import sys
import threading
import time
from pathlib import Path

_CONFIGURED = False

_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
# 带日期：服务可能跨天运行，排查时要能对上「什么时候挂的」
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# 这些库在 INFO 级过于聒噪（每次请求/每次 SQL），压到 WARNING
_NOISY = ("httpx", "httpcore", "urllib3", "sqlalchemy.engine", "watchfiles")

# uvicorn 的 logger 不走 root（propagate=False），必须单独挂 handler。
# ⚠️ 注意 `uvicorn.error` **不在**列表里：它默认 propagate=True 且自身无 handler，
# 会自然流到父 logger `uvicorn`（我们已挂 handler）——再给它单独挂一份会让同一条
# 日志被写两遍（2026-09-10 实测踩到）。attach 时会动态判断，见该函数。
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

_MAIN_BYTES = 5 * 1024 * 1024
_MAIN_BACKUPS = 5
_ERR_BYTES = 2 * 1024 * 1024
_ERR_BACKUPS = 3

# 心跳间隔（秒）。5 分钟够用且不吵；测试可用 NA_HEARTBEAT_SEC 调小。
_DEFAULT_HEARTBEAT_SEC = 300

_MAIN_FILE: logging.Handler | None = None
_ERR_FILE: logging.Handler | None = None
_HEARTBEAT_STARTED = False
_EXIT_HOOKED = False


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------
def _log_dir() -> Path:
    env = os.environ.get("NA_LOG_DIR")
    if env:
        return Path(env)
    # 本文件在 backend/app/core/ → parents[2] 即 backend/
    return Path(__file__).resolve().parents[2] / "logs"


def _mk_handler(path: Path, level: int, max_bytes: int, backups: int) -> logging.Handler | None:
    """建轮转文件 handler。**失败返回 None**——日志写不了绝不能拖垮服务启动。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        h = logging.handlers.RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
        )
        h.setLevel(level)
        h.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
        return h
    except Exception:
        return None


def _rss_mb() -> float | None:
    """当前进程物理内存占用（MB）。用 ctypes 读 Windows API，失败返回 None。"""
    try:
        import ctypes
        import ctypes.wintypes as wt

        class _PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wt.DWORD),
                ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        pmc = _PMC()
        pmc.cb = ctypes.sizeof(pmc)
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(  # type: ignore[attr-defined]
            ctypes.windll.kernel32.GetCurrentProcess(),  # type: ignore[attr-defined]
            ctypes.byref(pmc),
            pmc.cb,
        )
        if ok:
            return pmc.WorkingSetSize / 1024 / 1024
    except Exception:
        return None
    return None


def _install_exception_hooks() -> None:
    """挂上「未捕获异常」记录。链式调用原 hook，不吞掉别人的行为。"""
    prev_sys_hook = sys.excepthook

    def _sys_hook(exc_type, exc, tb):
        try:
            logging.getLogger("uncaught").critical(
                "已捕获未处理异常（主线程，进程通常随后退出）",
                exc_info=(exc_type, exc, tb),
            )
        except Exception:
            pass
        try:
            prev_sys_hook(exc_type, exc, tb)
        except Exception:
            pass

    sys.excepthook = _sys_hook

    # 后台线程：本项目大量用线程（写后摄取 / 工作流执行 / SSE），
    # 这些异常默认只打印到 stderr、窗口一关就查无此案 —— 必须落盘。
    if hasattr(threading, "excepthook"):
        prev_th_hook = threading.excepthook

        def _th_hook(args):
            try:
                logging.getLogger("uncaught").critical(
                    f"已捕获未处理异常（后台线程 thread={getattr(args.thread, 'name', '?')!r}）",
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
                )
            except Exception:
                pass
            try:
                prev_th_hook(args)
            except Exception:
                pass

        threading.excepthook = _th_hook  # type: ignore[assignment]


def _start_heartbeat() -> None:
    """后台心跳：定期记录「存活时刻 + 内存占用」。

    用途：进程被强杀时不会有任何退出日志，但**心跳的最后一条就是死亡时间**；
    内存持续上涨则可确诊泄漏——「运行着运行着就挂了」多半是这一类。
    """
    global _HEARTBEAT_STARTED
    if _HEARTBEAT_STARTED:
        return
    _HEARTBEAT_STARTED = True

    try:
        interval = float(os.environ.get("NA_HEARTBEAT_SEC", _DEFAULT_HEARTBEAT_SEC))
    except Exception:
        interval = float(_DEFAULT_HEARTBEAT_SEC)
    if interval <= 0:
        return

    def _loop():
        t0 = time.time()
        hb = logging.getLogger("app.heartbeat")
        while True:
            time.sleep(interval)
            try:
                rss = _rss_mb()
                mins = (time.time() - t0) / 60.0
                mem = f" RSS={rss:.0f}MB" if rss is not None else ""
                hb.info(
                    f"pid={os.getpid()} 已运行={mins:.1f}分钟{mem} "
                    f"线程={threading.active_count()}"
                )
            except Exception:
                pass

    threading.Thread(target=_loop, name="na-heartbeat", daemon=True).start()


def _log_exit() -> None:
    """进程退出标记。

    ★ 若日志里「有启动、无退出」，即说明是被强杀或硬崩溃（taskkill /F 不触发 atexit）。
    """
    try:
        logging.getLogger(__name__).info(
            f"进程退出 pid={os.getpid()}（优雅关闭）。"
            "⚠️ 若日志中查不到本行，说明进程是被强制结束或硬崩溃。"
        )
        for h in (_MAIN_FILE, _ERR_FILE):
            if h is not None:
                h.flush()
    except Exception:
        pass


def _register_exit_hook() -> None:
    global _EXIT_HOOKED
    if _EXIT_HOOKED:
        return
    # atexit 是 LIFO：本函数在 logging.shutdown 之后注册 → 会**先于**它执行，
    # 所以此刻 handler 还开着，能正常写盘。
    atexit.register(_log_exit)
    _EXIT_HOOKED = True


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------
def setup_logging(level: str | None = None) -> None:
    """初始化根 logger（幂等）：控制台 + 文件落盘 + 异常钩子 + 心跳 + 退出标记。

    级别优先级：参数 > 环境变量 NA_LOG_LEVEL > INFO。
    """
    global _CONFIGURED, _MAIN_FILE, _ERR_FILE
    if _CONFIGURED:
        return

    lvl_name = (level or os.environ.get("NA_LOG_LEVEL") or "INFO").upper()
    lvl = getattr(logging, lvl_name, logging.INFO)

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FORMAT, _DATEFMT))
        root.addHandler(handler)
    # 已有 handler（如被宿主预设）时不动它，只调级别

    # ---- 落盘（2026-09-10 新增）----
    log_dir = _log_dir()
    main_name = os.environ.get("NA_LOG_FILE", "backend.log")
    _MAIN_FILE = _mk_handler(log_dir / main_name, lvl, _MAIN_BYTES, _MAIN_BACKUPS)
    _ERR_FILE = _mk_handler(log_dir / "error.log", logging.WARNING, _ERR_BYTES, _ERR_BACKUPS)
    for h in (_MAIN_FILE, _ERR_FILE):
        if h is not None:
            root.addHandler(h)

    root.setLevel(lvl)

    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)

    _CONFIGURED = True

    attach_uvicorn_file_logging()
    _install_exception_hooks()
    _register_exit_hook()
    _start_heartbeat()

    logger = logging.getLogger(__name__)
    logger.info("=" * 64)
    logger.info(f"进程启动 pid={os.getpid()} 日志级别={lvl_name} 日志目录={log_dir}")
    if _MAIN_FILE is None or _ERR_FILE is None:
        logger.warning(
            "部分日志文件打开失败，本次仅输出到控制台（不影响服务运行）；"
            f"请检查目录是否可写：{log_dir}"
        )
    logger.info("=" * 64)


def _handled_by_ancestor(lg: logging.Logger, handlers: list) -> bool:
    """该 logger 的祖先链上是否已挂了我们其中某个 handler（避免同一日志写两遍）。"""
    parent = lg.parent
    while parent is not None:
        if any(h in parent.handlers for h in handlers):
            return True
        parent = parent.parent
    return False


def attach_uvicorn_file_logging() -> None:
    """把文件 handler 挂到 uvicorn 自己的 logger 上（幂等）。

    为什么需要单独挂：uvicorn 的 logger（uvicorn / uvicorn.access）默认
    `propagate=False` 且自带 handler，**不会流到 root**，于是「哪个请求把它打挂了」
    这类线索全在它手里。

    为什么要跳过某些 logger：`uvicorn.error` 默认 `propagate=True` 且自身无 handler，
    它会流到父 logger `uvicorn`。若给它也挂一份，同一条日志会被写两遍
    （2026-09-10 实测）。故凡是「会传播到已挂 handler 的祖先」的 logger 一律跳过。

    为什么 setup_logging 与 startup 各调一次：uvicorn 在 `Config.load()` 阶段会执行
    一次 `dictConfig`，若在它之前挂 handler 可能被冲掉；故应用启动后再幂等补挂一次。
    """
    handlers = [h for h in (_MAIN_FILE, _ERR_FILE) if h is not None]
    if not handlers:
        return
    # 顺序有讲究：先 `uvicorn`（挂上），再判断其子 logger 是否需要跳过
    for name in _UVICORN_LOGGERS:
        lg = logging.getLogger(name)
        if lg.propagate and _handled_by_ancestor(lg, handlers):
            continue
        for h in handlers:
            if h not in lg.handlers:
                lg.addHandler(h)
        # 它自带 handler 时级别已设定，这里只兜底 NOTSET 的情况
        if lg.level == logging.NOTSET:
            lg.setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """取模块 logger（顺带保证已初始化）。"""
    setup_logging()
    return logging.getLogger(name)
