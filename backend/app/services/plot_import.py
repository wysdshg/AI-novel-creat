"""小说导入管线（Phase 7.1）：给定小说目录 → 逐章概括 → 情节段切分 → 情节分类。

**模型**：硅基流动 `Qwen/Qwen3-8B`（``enable_thinking=false``，思考会吃光输出预算并拖慢 60s+）。
Key 复用 `app_configs.retrieval.siliconflow_key`（与向量检索同一把）。

**防限流（用户明确要求）**：
- 串行请求 + 每次请求最小间隔（默认 2s）；
- 429/5xx 指数退避（2/4/8/16/32s，最多 5 次）；
- 逐章概括按 (book_name, chapter_no) 幂等，中断重跑自动跳过已完成章节。

**版权**：只入库概括与结构模式，正文原文留在磁盘不进数据库。

三个入口（供 CLI / 未来向导页调用）：
- `import_chapters`   步骤 1-2：切章（文件名即章节）+ 逐章概括入库；
- `segment_chapters`  步骤 3：情节段切分（连续章归并为段 + 段概括）；
- `label_segments`    步骤 4：段打情节类型标签（"学院大比"这类，供跨书聚类参考）。
步骤 5「人工合并 + 凝练模板」需要人审，走向导页（下一轮）。
"""
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.orm import ChapterSummaryORM
from app.services.ingestion import parse_json_loose

logger = logging.getLogger(__name__)

SF_BASE = "https://api.siliconflow.cn/v1"
SF_MODEL = "Qwen/Qwen3-8B"
KEY_CONFIG_KEY = "retrieval.siliconflow_key"

# DeepSeek V4.1 Flash：arc 归并专用（见 merge_arcs 说明）
DS_BASE = "https://api.deepseek.com"
DS_MODEL = "deepseek-flash"
DS_KEY_CONFIG = "llm.deepseek_key"

MIN_INTERVAL_S = 2.0     # 请求最小间隔（防限流）
MAX_RETRY = 5            # 429/5xx 重试次数
MAX_CHAPTER_CHARS = 6000 # 送入 LLM 的单章正文上限（一章 3~4k 字足够）

_CH_FILE_RE = re.compile(r"^(?P<no>\d{2,6})\s*[_\- ]\s*(?P<title>.*)\.txt$", re.IGNORECASE)

_SEGMENT_SYS = "你是网文情节结构分析助手。只输出 JSON，不要输出任何其他文字。"


# ---------------------------------------------------------------------------
# 硅基流动直连（管线是离线批处理子系统，刻意不走 gateway：限速/退避/关思考全自控）
# ---------------------------------------------------------------------------
class RateLimiter:
    """全局请求限速器：保证相邻两次请求的**发起**间隔 >= min_interval。

    **线程安全**（2026-09-11 加锁）：并发概括时多个线程共用一个实例，
    不加锁会出现多个线程同时穿过判定 → 瞬间打爆限流。
    锁内 sleep 的语义是"请求发起被节流，但已发出的请求仍并行生成" ——
    这正是我们要的：RPM 受控，而生成阶段重叠。
    """

    def __init__(self, min_interval: float = MIN_INTERVAL_S):
        self._min = max(0.0, float(min_interval))
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.time()
            gap = now - self._last
            if gap < self._min:
                time.sleep(self._min - gap)
            self._last = time.time()


def sf_key(db: Session) -> str | None:
    """取硅基流动 Key（app_configs，SQLAlchemy JSON 列已自动反序列化）。"""
    from app.services import app_config
    v = app_config.get(db, KEY_CONFIG_KEY, None)
    if isinstance(v, str):
        v = v.strip()
        if v.startswith('"'):
            try:
                v = json.loads(v)
            except Exception:  # noqa: BLE001
                pass
    return v or None


def _chat_post(url: str, key: str, body: dict, *, timeout: int,
               rate: RateLimiter | None = None, label: str = "LLM",
               on_usage=None) -> str:
    """带限速 + 429/5xx 指数退避的 chat 调用（**厂商无关**，不含 db 依赖）。

    并发路径专用：Key 由调用方在主线程取好传进来（Session 非线程安全）。

    `on_usage(usage: dict, duration_ms: int, ok: bool)`（2026-09-13 加）：把厂商回传的
    `usage` 交给调用方记账。**用回调而不是直接 write** —— 本函数是线程无关的纯 HTTP 层，
    持 Session 会破坏"Session 非线程安全"的既有约定；且记账失败绝不冒泡（回调内部自吞）。
    """
    rate = rate or RateLimiter()
    last_err: Exception | None = None
    for attempt in range(MAX_RETRY):
        rate.wait()
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        _t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if on_usage:
                _safe_usage_cb(on_usage, data.get("usage"), int((time.time() - _t0) * 1000), True)
            return (data["choices"][0]["message"].get("content") or "").strip()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", "ignore")[:200]
            if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRY - 1:
                backoff = 2.0 ** (attempt + 1)
                logger.warning(f"[plot_import] {label} HTTP {e.code}，{backoff:.0f}s 后重试"
                               f"（{attempt + 1}/{MAX_RETRY}）: {err_body}")
                time.sleep(backoff)
                last_err = RuntimeError(f"HTTP {e.code}: {err_body}")
                continue
            if on_usage:
                _safe_usage_cb(on_usage, None, int((time.time() - _t0) * 1000), False)
            raise RuntimeError(f"{label} HTTP {e.code}: {err_body}") from e
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRY - 1:
                backoff = 2.0 ** (attempt + 1)
                logger.warning(f"[plot_import] {label} 请求异常，{backoff:.0f}s 后重试"
                               f"（{attempt + 1}/{MAX_RETRY}）: {type(e).__name__}: {e}")
                time.sleep(backoff)
                continue
            if on_usage:
                _safe_usage_cb(on_usage, None, int((time.time() - _t0) * 1000), False)
    raise RuntimeError(f"{label} 调用失败（重试 {MAX_RETRY} 次）: {last_err}")


def _safe_usage_cb(cb, usage, duration_ms: int, ok: bool) -> None:
    """调用记账回调，**任何异常都吞掉** —— 记账永远不许影响模型调用主链路。"""
    try:
        cb(usage, duration_ms, ok)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[plot_import] 用量回调失败（不影响调用）: {type(e).__name__}: {e}")


def _sf_post(key: str, user_content: str, *, max_tokens: int = 1024,
             temperature: float = 0.3, timeout: int = 120,
             rate: RateLimiter | None = None, on_usage=None) -> str:
    """硅基流动 Qwen3-8B（**关闭思考** —— Qwen3 思考默认开会吃光输出预算并拖慢 60s+）。"""
    body = {
        "model": SF_MODEL,
        "messages": [{"role": "user", "content": user_content}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "enable_thinking": False,
    }
    return _chat_post(SF_BASE + "/chat/completions", key, body,
                      timeout=timeout, rate=rate, label="硅基流动", on_usage=on_usage)


def ds_key(db: Session) -> str | None:
    """取 DeepSeek Key（app_configs.llm.deepseek_key）。"""
    from app.services import app_config
    v = app_config.get(db, DS_KEY_CONFIG, None)
    if isinstance(v, str):
        v = v.strip()
        if v.startswith('"'):
            try:
                v = json.loads(v)
            except Exception:  # noqa: BLE001
                pass
    return v or None


def _ds_post(key: str, user_content: str, *, max_tokens: int = 3000,
             temperature: float = 0.2, timeout: int = 300,
             rate: RateLimiter | None = None, on_usage=None) -> str:
    """DeepSeek V4.1 Flash（**关闭思考**）。

    实测（2026-09-11）：`deepseek-flash` 默认思考开，2000 token 预算全被 reasoning 吃光、
    content 返回空且耗时 10.7s；加 `thinking={"type":"disabled"}` 后 **1.7s** 拿到完整 JSON。

    `on_usage`（2026-09-13 加）：DeepSeek 回传 `usage.prompt_cache_hit_tokens` /
    `prompt_cache_miss_tokens` —— 这两档单价差 50 倍，必须落库才能做成本分析。
    """
    body = {
        "model": DS_MODEL,
        "messages": [{"role": "user", "content": user_content}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "thinking": {"type": "disabled"},
    }
    return _chat_post(DS_BASE + "/chat/completions", key, body,
                      timeout=timeout, rate=rate, label="DeepSeek", on_usage=on_usage)


def make_usage_cb(scene: str, *, project_id: str | None = None):
    """构造一个**自带独立 Session** 的记账回调（离线管线专用，2026-09-13）。

    为什么不自带 Session：`_chat_post` 可能在**并发线程**里执行，而 SQLAlchemy Session
    非线程安全（见 docs/04）。回调在**调用它的那个线程**里现开现关一个 Session，
    天然线程安全，且不会与调用方的事务纠缠。

    失败一律静默：记账是旁路，永远不许影响模型调用。
    """
    def _cb(usage, duration_ms: int, ok: bool) -> None:
        try:
            from app.core import database
            from app.services import usage_crud
            database.get_engine()          # 确保 SessionLocal 已初始化（惰性全局）
            db = database.SessionLocal()
            try:
                usage_crud.record_usage(
                    db, scene=scene, vendor="deepseek" if scene.startswith("ds_") else "siliconflow",
                    model_name=DS_MODEL if scene.startswith("ds_") else SF_MODEL,
                    usage=usage, project_id=project_id,
                    duration_ms=duration_ms, ok=ok,
                )
            finally:
                db.close()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[plot_import] 用量记账失败（不影响调用）scene={scene}: "
                           f"{type(e).__name__}: {e}")
    return _cb


def sf_chat(db: Session, user_content: str, *, scene: str = "sf_chat", **kw) -> str:
    """调用硅基流动 Qwen3-8B（关闭思考）。429/5xx 指数退避。失败抛 RuntimeError。

    带 Key 解析的封装（串行路径用）；并发路径请用 `_sf_post` + 主线程预取的 Key。

    `scene`（2026-09-13）：用量记账的场景名，便于按用途拆分成本。
    串行路径直接复用调用方的 session 记账（同线程，安全）。
    """
    key = sf_key(db)
    if not key:
        raise RuntimeError("未配置硅基流动 Key（app_configs.retrieval.siliconflow_key）")

    def _cb(usage, duration_ms: int, ok: bool) -> None:
        from app.services import usage_crud
        usage_crud.record_usage(db, scene=scene, vendor="siliconflow",
                                model_name=SF_MODEL, usage=usage,
                                duration_ms=duration_ms, ok=ok)

    kw.setdefault("on_usage", _cb)
    return _sf_post(key, user_content, **kw)


# ---------------------------------------------------------------------------
# 步骤 1：章节发现与读取
# ---------------------------------------------------------------------------
def discover_chapters(book_dir: str) -> list[dict]:
    """扫描目录，按文件名 `0001_章法宝坟墓.txt` 识别章节。返回按章号升序。"""
    out: list[dict] = []
    for p in sorted(Path(book_dir).glob("*.txt")):
        m = _CH_FILE_RE.match(p.name)
        if m:
            out.append({
                "no": int(m.group("no")),
                "title": m.group("title").strip(),
                "path": str(p),
            })
    return out


def read_text(path: str) -> str:
    raw = Path(path).read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gb18030", errors="ignore")


# ---------------------------------------------------------------------------
# 步骤 2：逐章概括（幂等，断点续跑）
# ---------------------------------------------------------------------------
def _valid_summary(s: str) -> bool:
    """概括有效性粗校验：挡住"解析残渣/错误说明"被当成概括写进库。

    真实概括 80~120 字，15 字是很宽的下限；另挡 JSON 残片特征。
    （2026-09-11：单测暴露出补跑路径没校验，会把 "这不是 JSON" 原样入库）
    """
    if not s or len(s) < 15:
        return False
    if "chapters" in s or s.lstrip().startswith(("{", "[")):
        return False
    return True


def _summarize_prompt(title: str, text: str) -> str:
    return (
        "请用 80~120 字概括这一章的主要情节。要求：\n"
        "1. 只记客观事件：谁、在哪、做了什么、结果如何；\n"
        "2. 记录新出场人物（带身份）与重要物品/地点；\n"
        "3. 不要评价文笔，不要猜测后续，不要用「本章讲述了」开头。\n"
        f"\n章节标题：{title}\n\n正文：\n{text[:MAX_CHAPTER_CHARS]}"
    )


def import_chapters(db: Session, book_dir: str, book_name: str, *,
                    start: int = 1, end: int | None = None,
                    rate: RateLimiter | None = None,
                    progress=None) -> dict:
    """逐章概括入库。幂等：已存在的 (book_name, chapter_no) 跳过。"""
    chs = discover_chapters(book_dir)
    if not chs:
        raise RuntimeError(f"目录中未发现章节文件（需形如 0001_标题.txt）: {book_dir}")
    rate = rate or RateLimiter()
    done = skipped = failed = 0
    for ch in chs:
        if ch["no"] < start or (end and ch["no"] > end):
            continue
        if db.query(ChapterSummaryORM).filter_by(
                book_name=book_name, chapter_no=ch["no"]).first():
            skipped += 1
            continue
        text = read_text(ch["path"])
        try:
            summ = sf_chat(db, _summarize_prompt(ch["title"], text),
                           max_tokens=512, temperature=0.2, rate=rate,
                           scene="sf_summarize")
        except Exception as e:  # noqa: BLE001
            failed += 1
            logger.warning(f"[plot_import] 第{ch['no']}章概括失败（跳过，重跑会补）: "
                           f"{type(e).__name__}: {e}")
            continue
        db.add(ChapterSummaryORM(
            id=uuid.uuid4().hex,
            book_name=book_name,
            chapter_no=ch["no"],
            title=ch["title"] or None,
            summary=summ,
            created_at=datetime.utcnow(),
        ))
        db.commit()
        done += 1
        if progress:
            progress(ch["no"], done, skipped, failed)
    return {"done": done, "skipped": skipped, "failed": failed, "total_files": len(chs)}


def _batch_prompt(items: list[dict]) -> str:
    """一次让模型概括连续 N 章（items: [{no, title, text}]）。"""
    blocks = [
        f"【第{it['no']}章 {it['title']}】\n{it['text'][:MAX_CHAPTER_CHARS]}"
        for it in items
    ]
    n = len(items)
    return (
        f"下面是连续 {n} 章的正文。请**为每一章分别**写 80~120 字概括。要求：\n"
        "1. 只记客观事件：谁、在哪、做了什么、结果如何；\n"
        "2. 记录新出场人物（带身份）与重要物品/地点；\n"
        "3. 不要评价文笔，不要猜测后续，不要用「本章讲述了」开头；\n"
        "4. 每章概括**独立完整**，不要把多章揉成一段。\n\n"
        "只输出 JSON（不要 markdown 代码块、不要任何额外说明）：\n"
        '{"chapters":[{"no":章号,"summary":"概括"},...]}\n\n'
        + "\n\n".join(blocks)
    )


def import_chapters_batch(db: Session, book_dir: str, book_name: str, *,
                          batch_size: int = 3, concurrency: int = 1,
                          start: int = 1, end: int | None = None,
                          rate: RateLimiter | None = None,
                          progress=None) -> dict:
    """批量概括入库（每 batch_size 章一次调用）+ 可选并发。**幂等语义同 import_chapters**。

    为什么这么做（2026-09-11 实测设计）：
    - 请求数降到 1/batch_size → 限流压力大降（1671 章：1671 次 → 557 次）；
    - 模型一次看到连续 N 章 → 跨章事件（一场战斗跨几章）概括更连贯；
    - 并发让"等生成"的时间重叠 —— **真正的瓶颈是等模型生成，不是限速间隔**。

    线程模型：**LLM 调用在工作线程（纯 IO），DB 写入全部回主线程串行** ——
    SQLAlchemy Session 非线程安全，这样既拿到并发又避开多线程写 SQLite。
    """
    chs = discover_chapters(book_dir)
    if not chs:
        raise RuntimeError(f"目录中未发现章节文件（需形如 0001_标题.txt）: {book_dir}")

    pending: list[dict] = []
    skipped = 0
    for ch in chs:
        if ch["no"] < start or (end and ch["no"] > end):
            continue
        if db.query(ChapterSummaryORM).filter_by(
                book_name=book_name, chapter_no=ch["no"]).first():
            skipped += 1
            continue
        pending.append(ch)

    if not pending:
        return {"done": 0, "skipped": skipped, "failed": 0, "batches": 0,
                "total_files": len(chs)}

    key = sf_key(db)      # 主线程取 Key（工作线程不碰 session）
    if not key:
        raise RuntimeError("未配置硅基流动 Key（app_configs.retrieval.siliconflow_key）")
    rate = rate or RateLimiter()
    bs = max(1, int(batch_size))
    batches = [pending[i:i + bs] for i in range(0, len(pending), bs)]

    # 记账回调（2026-09-13）：工作线程里现开现关独立 Session —— 天然的线程安全，
    # 且与主线程的写库事务完全隔离。
    on_usage = make_usage_cb("sf_summarize")

    def run_batch(batch: list[dict]):
        """工作线程：只读磁盘 + 网络，不碰 session。"""
        items = [{"no": c["no"], "title": c["title"], "text": read_text(c["path"])}
                 for c in batch]
        raw = _sf_post(key, _batch_prompt(items), max_tokens=400 * len(batch),
                       temperature=0.2, rate=rate, on_usage=on_usage)
        data = parse_json_loose(raw) or {}
        got: dict[int, str] = {}
        for row in data.get("chapters") or []:
            try:
                no = int(row.get("no"))
            except (TypeError, ValueError):
                continue
            s = str(row.get("summary") or "").strip()
            if s and _valid_summary(s):
                got[no] = s
        return batch, got

    results: list[tuple[list, dict]] = []
    failed_batches = 0
    if int(concurrency or 1) > 1:
        with ThreadPoolExecutor(max_workers=int(concurrency)) as ex:
            futs = [ex.submit(run_batch, b) for b in batches]
            for fut in as_completed(futs):
                try:
                    results.append(fut.result())
                except Exception as e:  # noqa: BLE001
                    failed_batches += 1
                    logger.warning(f"[plot_import] 批次失败（重跑同一命令会自动补）: "
                                   f"{type(e).__name__}: {e}")
    else:
        for b in batches:
            try:
                results.append(run_batch(b))
            except Exception as e:  # noqa: BLE001
                failed_batches += 1
                logger.warning(f"[plot_import] 批次失败（重跑同一命令会自动补）: "
                               f"{type(e).__name__}: {e}")

    # 主线程串行写库
    done = failed = 0
    missed: list[dict] = []
    for batch, got in results:
        for c in batch:
            s = got.get(c["no"])
            if not s:
                missed.append(c)       # 批内漏章，稍后单章补跑
                continue
            db.add(ChapterSummaryORM(
                id=uuid.uuid4().hex,
                book_name=book_name,
                chapter_no=c["no"],
                title=c["title"] or None,
                summary=s,
                created_at=datetime.utcnow(),
            ))
            done += 1
        db.commit()
        if progress:
            progress(batch[-1]["no"], done, skipped, failed)

    # 漏章补跑（2026-09-11 实测：批量模式下 8B 偶尔漏掉批内某章）。
    # 策略分两级：**优先把漏章重新凑批再跑一轮批量**（省得多：3 章批量 ~15s vs 单章 3×30s），
    # 仍漏的才用单章兜底（极少发生）。不依赖"下次重跑命令"来兜，让单轮尽量补齐。
    retried = 0
    if missed:
        retried = len(missed)
        still_missing: list[dict] = []
        for sb in [missed[i:i + bs] for i in range(0, len(missed), bs)]:
            try:
                _, got = run_batch(sb)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[plot_import] 漏章批量补跑失败: {type(e).__name__}: {e}")
                got = {}
            for c in sb:
                s = got.get(c["no"])
                if not s:
                    still_missing.append(c)
                    continue
                db.add(ChapterSummaryORM(
                    id=uuid.uuid4().hex, book_name=book_name, chapter_no=c["no"],
                    title=c["title"] or None, summary=s, created_at=datetime.utcnow()))
                done += 1
        db.commit()

        # 兜底：批量仍漏的用单章 prompt（更简单、成功率更高）
        for c in still_missing:
            try:
                s = _sf_post(key, _summarize_prompt(c["title"], read_text(c["path"])),
                             max_tokens=512, temperature=0.2, rate=rate,
                             on_usage=make_usage_cb("sf_summarize")).strip()
                if not _valid_summary(s):
                    s = ""
            except Exception as e:  # noqa: BLE001
                s = ""
                logger.warning(f"[plot_import] 第{c['no']}章单章补跑失败（重跑命令可再补）: "
                               f"{type(e).__name__}: {e}")
            if not s:
                failed += 1
                continue
            db.add(ChapterSummaryORM(
                id=uuid.uuid4().hex, book_name=book_name, chapter_no=c["no"],
                title=c["title"] or None, summary=s, created_at=datetime.utcnow()))
            done += 1
        db.commit()
        logger.info(f"[plot_import] 漏章补跑：{retried} 章，批量+单章兜底后仍失败 {failed}")

    return {"done": done, "skipped": skipped, "failed": failed,
            "failed_batches": failed_batches, "batches": len(batches),
            "retried": retried, "total_files": len(chs)}


# ---------------------------------------------------------------------------
# 步骤 3：情节段切分
# ---------------------------------------------------------------------------
def _segment_prompt(numbered: str, prev_tail: str | None) -> str:
    ctx = f"\n（上一批最后一段的概括，供衔接参考：{prev_tail}）\n" if prev_tail else ""
    return (
        "下面是一部小说**连续若干章**的逐章概括。请把它们划分为若干「情节段」：\n"
        "- 每段 2~6 章，是一个相对完整的小故事（有起因、发展、结果）；\n"
        "- 每段输出 100~200 字概括，讲清起因→发展→结果；\n"
        "- 覆盖全部章节，段与段不重叠不遗漏；\n"
        "- 章节连续出现在同一段就按升序列出章号。\n"
        f"{ctx}\n输出 JSON：{{\"segments\": [{{\"chapters\": [1,2,3], \"summary\": \"…\"}}]}}\n"
        f"\n{numbered}"
    )


def segment_chapters(db: Session, book_name: str, *, batch: int = 10,
                     concurrency: int = 1, force: bool = False,
                     rate: RateLimiter | None = None,
                     progress=None) -> dict:
    """情节段切分：每批 batch 章交给 LLM 划段，写回 segment_no / segment_summary。

    **断点续跑（2026-09-11 加，重要）**：从前往后，**前缀内全部完成的批次直接跳过**，
    段号从已有最大段号续接。原因：长任务会被外部超时中断（实测 OpenCode 的 shell 有 25 分钟超时），
    而段切分是全书序列操作 —— 以前每次重跑都从零重算，存在"反复超时、永远跑不完"的风险。
    `force=True` 才清空重算（想整体重切时用）。

    **并发**：批次之间**没有顺序依赖**（不再用上批 tail 做衔接参考），可 `concurrency>1` 并行取结果；
    但**段号在主线程按章节顺序分配**（顺序不会乱）。
    """
    rows = (
        db.query(ChapterSummaryORM)
        .filter_by(book_name=book_name)
        .order_by(ChapterSummaryORM.chapter_no)
        .all()
    )
    rows = [r for r in rows if (r.summary or "").strip()]
    if len(rows) < 2:
        return {"segments": 0, "chapters": len(rows), "skipped_batches": 0,
                "batches_run": 0}

    if force:
        for r in rows:
            r.segment_no = None
            r.segment_summary = None
        db.commit()

    bs = max(1, int(batch))
    batch_specs = [rows[i:i + bs] for i in range(0, len(rows), bs)]

    # 前缀式跳过：从前往后，遇到第一个未完成批次就停（保证段号顺序一致）
    start_idx = 0
    for bi, b_rows in enumerate(batch_specs):
        if all(r.segment_no is not None for r in b_rows):
            start_idx = bi + 1
        else:
            break
    todo = list(enumerate(batch_specs))[start_idx:]
    skipped_batches = start_idx

    max_seg = (
        db.query(func.max(ChapterSummaryORM.segment_no))
        .filter_by(book_name=book_name)
        .scalar()
    ) or 0

    if not todo:
        return {"segments": max_seg, "chapters": len(rows),
                "skipped_batches": skipped_batches, "batches_run": 0,
                "note": "全部批次已完成"}

    key = sf_key(db)
    if not key:
        raise RuntimeError("未配置硅基流动 Key（app_configs.retrieval.siliconflow_key）")
    rate = rate or RateLimiter()

    def run_batch(b_rows: list) -> dict:
        numbered = "\n".join(f"第{r.chapter_no}章：{r.summary}" for r in b_rows)
        raw = _sf_post(key, _segment_prompt(numbered, None), max_tokens=256 * len(b_rows),
                       temperature=0.2, rate=rate, on_usage=make_usage_cb("sf_segment"))
        return parse_json_loose(raw) or {}

    results: dict[int, dict] = {}
    if int(concurrency or 1) > 1 and len(todo) > 1:
        with ThreadPoolExecutor(max_workers=int(concurrency)) as ex:
            futs = {ex.submit(run_batch, b_rows): bi for bi, b_rows in todo}
            for fut in as_completed(futs):
                bi = futs[fut]
                try:
                    results[bi] = fut.result()
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"[plot_import] 段切分批次失败（重跑会补）: "
                                   f"{type(e).__name__}: {e}")
                    results[bi] = {}
    else:
        for bi, b_rows in todo:
            try:
                results[bi] = run_batch(b_rows)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"[plot_import] 段切分批次失败（重跑会补）: "
                               f"{type(e).__name__}: {e}")
                results[bi] = {}

    # 主线程按章节顺序分配段号 + 逐批落库（进度可观测、中断不丢已完成批次）
    seg_no = max_seg + 1
    done_chapters = 0
    for i, (bi, b_rows) in enumerate(todo):
        segs = (results.get(bi) or {}).get("segments") or []
        if not segs:
            logger.warning(f"[plot_import] 段切分批次未解析出 JSON（第 {b_rows[0].chapter_no}"
                           f"~{b_rows[-1].chapter_no} 章），整批回退为单段")
            segs = [{"chapters": [r.chapter_no for r in b_rows],
                     "summary": "。".join(r.summary for r in b_rows)[:200]}]
        covered: set[int] = set()
        for seg in segs:
            summary = (seg.get("summary") or "").strip()
            hit_any = False
            for no in seg.get("chapters") or []:
                hit = next((r for r in b_rows if r.chapter_no == no), None)
                if hit is None or no in covered:
                    continue
                hit.segment_no = seg_no
                hit.segment_summary = summary
                covered.add(no)
                hit_any = True
            if hit_any:
                seg_no += 1
        for r in b_rows:          # 漏标兜底：归入上一段，保证全覆盖
            if r.segment_no is None:
                r.segment_no = max(1, seg_no - 1)
        db.commit()
        done_chapters += len(b_rows)
        logger.info(f"[plot_import] 段切分进度 {start_idx * bs + done_chapters}/{len(rows)} 章")
        if progress:
            progress(start_idx * bs + done_chapters, len(rows))
    return {"segments": seg_no - 1, "chapters": len(rows),
            "skipped_batches": skipped_batches, "batches_run": len(todo)}


# ---------------------------------------------------------------------------
# 步骤 4：段分类（情节类型标签）
# ---------------------------------------------------------------------------
def export_report(db: Session, book_name: str, out_path: str | None = None) -> str:
    """把处理结果导出为可读 Markdown 报告。返回写入路径。

    结构随数据层级自适应：
    - **有弧 → 三级**（弧 → 段 → 章）—— 人工审核"弧归并是否合理"的主要窗口；
    - 无弧 → 段级（旧行为）。
    """
    rows = (
        db.query(ChapterSummaryORM)
        .filter_by(book_name=book_name)
        .order_by(ChapterSummaryORM.chapter_no)
        .all()
    )
    # 聚合：arc → segment → chapters（无弧时统一落进 None 桶）
    arcs: dict = {}
    for r in rows:
        a = arcs.setdefault(r.arc_no, {"name": None, "summary": None, "segs": {}})
        if r.arc_name:
            a["name"] = r.arc_name
        if r.arc_summary:
            a["summary"] = r.arc_summary
        s = a["segs"].setdefault(r.segment_no, {"label": None, "summary": None, "chapters": []})
        s["chapters"].append(r)
        if r.segment_summary:
            s["summary"] = r.segment_summary
        if r.plot_label:
            s["label"] = r.plot_label

    n_segs = len({r.segment_no for r in rows})
    has_arc = any(k is not None for k in arcs)
    out: list[str] = [
        f"# 导入报告 · 《{book_name}》",
        "",
        f"- 章节：{len(rows)} 章 ｜ 情节段：{n_segs} 段"
        + (f" ｜ 故事弧：{len([k for k in arcs if k is not None])} 个" if has_arc else ""),
        f"- 模型：{SF_MODEL}（概括 / 段切分 / 分类）"
        + (f" + {DS_MODEL}（弧归并）" if has_arc else ""),
        "",
        "---",
        "",
    ]

    def emit_seg(s_no, s, prefix: str) -> None:
        nos = "、".join(str(r.chapter_no) for r in s["chapters"])
        title = f"段 {s_no}" if s_no is not None else "未分段"
        out.append(f"{prefix}{title} · {s['label'] or '—'}（第 {nos} 章）")
        out.append("")
        out.append(f"**段概括**：{s['summary'] or '—'}")
        out.append("")
        for r in s["chapters"]:
            out.append(f"- **第 {r.chapter_no} 章 {r.title or ''}**：{r.summary}")
        out.append("")

    def _sorted(d: dict):
        return sorted(d.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))

    if has_arc:
        for a_no, a in _sorted(arcs):
            if a_no is None:
                if not a["segs"]:
                    continue
                out.append(f"## 未归弧（{len(a['segs'])} 段）")
                out.append("")
                for s_no, s in _sorted(a["segs"]):
                    emit_seg(s_no, s, "### ")
                continue
            chs = [c.chapter_no for s in a["segs"].values() for c in s["chapters"]]
            rng = f"第 {min(chs)}~{max(chs)} 章" if chs else "—"
            out.append(f"## 弧 {a_no} · {a['name'] or '—'}（{rng}）")
            out.append("")
            out.append(f"**弧概括**：{a['summary'] or '—'}")
            out.append("")
            for s_no, s in _sorted(a["segs"]):
                emit_seg(s_no, s, "### ")
    else:
        for s_no, s in _sorted(arcs.get(None, {"segs": {}})["segs"]):
            emit_seg(s_no, s, "## ")

    if out_path is None:
        # backend/app/services/plot_import.py → parents[3] = 项目根（[0]=services,[1]=app,[2]=backend）
        root = Path(__file__).resolve().parents[3]
        out_path = str(root / "outputs" / f"{book_name}-导入报告.md")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(out), encoding="utf-8")
    return out_path


def label_segments(db: Session, book_name: str, *,
                   rate: RateLimiter | None = None) -> dict:
    """给每个情节段打情节类型标签（4~8 字），写回该段全部章的 plot_label。"""
    rate = rate or RateLimiter()
    rows = (
        db.query(ChapterSummaryORM)
        .filter_by(book_name=book_name)
        .filter(ChapterSummaryORM.segment_no.isnot(None))
        .order_by(ChapterSummaryORM.segment_no, ChapterSummaryORM.chapter_no)
        .all()
    )
    segs: dict[int, list[ChapterSummaryORM]] = {}
    for r in rows:
        segs.setdefault(r.segment_no, []).append(r)
    labeled = 0
    for seg_no, seg_rows in sorted(segs.items()):
        summary = seg_rows[0].segment_summary or "。".join(r.summary for r in seg_rows)[:200]
        try:
            label = sf_chat(
                db,
                "下面是小说的一个情节段概括。请给它一个「情节类型」标签（4~8 字，"
                "如：学院大比/秘境寻宝/势力冲突/日常过渡/升级突破/结盟交涉/追逃猎杀）。"
                "只输出标签本身，不要引号和句号。\n\n" + summary,
                max_tokens=32, temperature=0.2, rate=rate, scene="sf_label",
            )
            label = label.strip().strip("「」\"'。.")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[plot_import] 段 {seg_no} 分类失败（跳过）: {type(e).__name__}: {e}")
            continue
        if not label:
            continue
        for r in seg_rows:
            r.plot_label = label
        labeled += 1
    db.commit()
    return {"segments": len(segs), "labeled": labeled}


# ---------------------------------------------------------------------------
# 步骤 6：故事弧归并（arc 层 —— 模板真正的候选单元）
# ---------------------------------------------------------------------------
def _arc_prompt(seg_list: list[dict]) -> str:
    """seg_list: [{no, summary, chapters:[...]}]"""
    lines = [
        f"段{s['no']}（第 {s['chapters'][0]}~{s['chapters'][-1]} 章）：{s['summary']}"
        for s in seg_list
    ]
    return (
        f"下面是一部小说连续 {len(seg_list)} 个情节段的概括。请把它们归并为若干「故事弧」。\n"
        "「故事弧」的定义：一个有完整冲突升级链的故事单元（通常含 2~6 个情节段），\n"
        "也就是读者感知到的「一个完整套路 / 一个爽点周期」（例如：金手指觉醒、冲突升级与备战、家族危机）。\n\n"
        "要求：\n"
        "1. 每个弧输出 80~150 字概括，讲清这条弧的起因 → 升级 → 转折 → 结果；\n"
        "2. 覆盖全部情节段，不重叠不遗漏；同一个弧里的段号必须连续；\n"
        "3. 给每个弧起一个 4~8 字的名称。\n\n"
        "只输出 JSON（不要 markdown 代码块、不要任何额外说明）：\n"
        '{"arcs":[{"segments":[段号...],"name":"弧名","summary":"概括"}]}\n\n'
        + "\n".join(lines)
    )


def merge_arcs(db: Session, book_name: str, *, rate: RateLimiter | None = None,
               max_tokens: int = 16000, chunk: int = 120) -> dict:
    """把情节段归并为故事弧（Phase 7.1 arc 层，2026-09-11）。

    **为什么需要这一层**：段（beat）是"事件粒度"，而模板需要的单元是"故事弧"
    （一个完整套路 = 一个爽点周期，8~15 章）。只有段层时，切出来的段"单独看没毛病、
    但不像一个完整篇章"—— 缺的就是这层归并。

    **模型升档**：Qwen3-8B 做局部概括（机械活）够用，但"看懂全局叙事结构"是强语义任务 →
    用 DeepSeek V4.1 Flash（输入几千 token，一次几厘钱）。

    幂等：每次重算先清空该书的旧 arc 标记。未覆盖的段兜底归入最后一个弧。
    """
    rows = (
        db.query(ChapterSummaryORM)
        .filter_by(book_name=book_name)
        .order_by(ChapterSummaryORM.chapter_no)
        .all()
    )
    rows = [r for r in rows if r.segment_no is not None]
    if not rows:
        return {"arcs": 0, "segments": 0, "error": "没有段数据（请先跑 --stage segment）"}

    segs: dict[int, list] = {}
    for r in rows:
        segs.setdefault(r.segment_no, []).append(r)
    seg_list = [
        {
            "no": no,
            "summary": srows[0].segment_summary or "。".join(x.summary for x in srows)[:200],
            "chapters": [x.chapter_no for x in srows],
        }
        for no, srows in sorted(segs.items())
    ]

    for r in rows:          # 重算前清旧标记
        r.arc_no = None
        r.arc_name = None
        r.arc_summary = None
    db.commit()

    key = ds_key(db)
    if not key:
        raise RuntimeError("未配置 DeepSeek Key（app_configs.llm.deepseek_key）")
    rate = rate or RateLimiter()

    # 分批归并：段数多了单次输出会超过 max_tokens 被**截断** → JSON 解析失败
    # （2026-09-11 实测教训：斗破 84 段一次归并，max_tokens=3000 直接截断，arcs 全丢）
    batches = [seg_list[i:i + max(1, chunk)] for i in range(0, len(seg_list), max(1, chunk))]
    arcs: list[dict] = []
    raws: list[str] = []
    for b in batches:
        raw = _ds_post(key, _arc_prompt(b), max_tokens=max_tokens, rate=rate,
                       on_usage=make_usage_cb("ds_arc"))
        raws.append(raw)
        got = (parse_json_loose(raw) or {}).get("arcs") or []
        if not got:
            logger.warning(f"[plot_import] arc 归并批次（段 {b[0]['no']}~{b[-1]['no']}）"
                           f"未解析出 JSON: {raw[:150]!r}")
        arcs.extend(got)
    if not arcs:
        logger.warning(f"[plot_import] arc 归并整体未解析出 JSON（段数据保留不动）: "
                       f"{raws[0][:160]!r}" if raws else "")
        return {"arcs": 0, "segments": len(seg_list), "error": "JSON 解析失败",
                "raw_head": (raws[0] if raws else "")[:200]}

    covered: set[int] = set()
    n_arcs = 0
    for arc in arcs:
        seg_nos: list[int] = []
        for x in arc.get("segments") or []:
            try:
                seg_nos.append(int(x))
            except (TypeError, ValueError):
                continue
        name = (arc.get("name") or "").strip()
        summ = (arc.get("summary") or "").strip()
        targets = [sn for sn in seg_nos if sn in segs and sn not in covered]
        if not targets:
            continue
        n_arcs += 1
        for sn in targets:
            covered.add(sn)
            for r in segs[sn]:
                r.arc_no = n_arcs
                r.arc_name = name or None
                r.arc_summary = summ or None
    leftover = [sn for sn in segs if sn not in covered]
    if leftover:
        if n_arcs == 0:
            n_arcs = 1
        for sn in leftover:          # 兜底：保证全覆盖（否则报告里会丢段）
            for r in segs[sn]:
                r.arc_no = n_arcs
        logger.warning(f"[plot_import] {len(leftover)} 个段未被归并，已兜底归入最后一个弧")
    db.commit()
    return {"arcs": n_arcs, "segments": len(seg_list),
            "covered": len(covered), "leftover": len(leftover)}
