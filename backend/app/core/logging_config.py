"""统一日志配置（Phase 0.2 / B2）。

背景：全项目 80+ 处 `print`——无级别、无时间戳、无模块标记、无法按模块过滤，
排查问题时只能肉眼扫屏，且后台线程（写后摄取）的输出与请求日志混在一起分不开。

用法：
    from app.core.logging_config import get_logger
    logger = logging.getLogger(__name__)   # 亦可，setup 已在 import 时完成
    logger.info("...")
    logger.warning("...")   # 失败/异常/降级

约定：
- **保留控制台输出**（本机单人工具，看终端是主要排查方式），但不是简单替换 print：
  加了级别 + 时间 + 模块名，可用 NA_LOG_LEVEL 控制；
- uvicorn 自己的 logger 不受影响（它挂在自己的 logger 上，不重复打印）；
- 第三方库的噪声压到 WARNING。
"""
import logging
import os
import sys

_CONFIGURED = False

_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
_DATEFMT = "%H:%M:%S"

# 这些库在 INFO 级过于聒噪（每次请求/每次 SQL），压到 WARNING
_NOISY = ("httpx", "httpcore", "urllib3", "sqlalchemy.engine", "watchfiles")


def setup_logging(level: str | None = None) -> None:
    """初始化根 logger（幂等）。级别优先级：参数 > 环境变量 NA_LOG_LEVEL > INFO。"""
    global _CONFIGURED
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
    root.setLevel(lvl)

    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """取模块 logger（顺带保证已初始化）。"""
    setup_logging()
    return logging.getLogger(name)
