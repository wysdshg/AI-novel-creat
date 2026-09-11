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
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.orm import ChapterSummaryORM
from app.services.ingestion import parse_json_loose

logger = logging.getLogger(__name__)

SF_BASE = "https://api.siliconflow.cn/v1"
SF_MODEL = "Qwen/Qwen3-8B"
KEY_CONFIG_KEY = "retrieval.siliconflow_key"

MIN_INTERVAL_S = 2.0     # 请求最小间隔（防限流）
MAX_RETRY = 5            # 429/5xx 重试次数
MAX_CHAPTER_CHARS = 6000 # 送入 LLM 的单章正文上限（一章 3~4k 字足够）

_CH_FILE_RE = re.compile(r"^(?P<no>\d{2,6})\s*[_\- ]\s*(?P<title>.*)\.txt$", re.IGNORECASE)

_SEGMENT_SYS = "你是网文情节结构分析助手。只输出 JSON，不要输出任何其他文字。"


# ---------------------------------------------------------------------------
# 硅基流动直连（管线是离线批处理子系统，刻意不走 gateway：限速/退避/关思考全自控）
# ---------------------------------------------------------------------------
class RateLimiter:
    """串行限速器：保证相邻两次请求间隔 >= min_interval。"""

    def __init__(self, min_interval: float = MIN_INTERVAL_S):
        self._min = max(0.0, float(min_interval))
        self._last = 0.0

    def wait(self) -> None:
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


def sf_chat(db: Session, user_content: str, *, max_tokens: int = 1024,
            temperature: float = 0.3, timeout: int = 120,
            rate: RateLimiter | None = None) -> str:
    """调用硅基流动 Qwen3-8B（关闭思考）。429/5xx 指数退避。失败抛 RuntimeError。"""
    key = sf_key(db)
    if not key:
        raise RuntimeError("未配置硅基流动 Key（app_configs.retrieval.siliconflow_key）")
    rate = rate or RateLimiter()
    body = {
        "model": SF_MODEL,
        "messages": [{"role": "user", "content": user_content}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "enable_thinking": False,   # Qwen3 系思考默认开：会吃光输出预算并拖慢 60s+
    }
    last_err: Exception | None = None
    for attempt in range(MAX_RETRY):
        rate.wait()
        req = urllib.request.Request(
            SF_BASE + "/chat/completions",
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return (data["choices"][0]["message"].get("content") or "").strip()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", "ignore")[:200]
            if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRY - 1:
                backoff = 2.0 ** (attempt + 1)
                logger.warning(f"[plot_import] HTTP {e.code}，{backoff:.0f}s 后重试"
                               f"（{attempt + 1}/{MAX_RETRY}）: {err_body}")
                time.sleep(backoff)
                last_err = RuntimeError(f"HTTP {e.code}: {err_body}")
                continue
            raise RuntimeError(f"硅基流动 HTTP {e.code}: {err_body}") from e
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRY - 1:
                time.sleep(2.0 ** (attempt + 1))
                continue
    raise RuntimeError(f"硅基流动调用失败（重试 {MAX_RETRY} 次）: {last_err}")


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
                           max_tokens=512, temperature=0.2, rate=rate)
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
                     rate: RateLimiter | None = None,
                     progress=None) -> dict:
    """情节段切分：每批 batch 章交给 LLM 划段，写回 segment_no / segment_summary。

    幂等：每次重算会**先清空**该书的旧段标记。跨批次边界接受近似（MVP）。
    """
    rows = (
        db.query(ChapterSummaryORM)
        .filter_by(book_name=book_name)
        .order_by(ChapterSummaryORM.chapter_no)
        .all()
    )
    rows = [r for r in rows if (r.summary or "").strip()]
    if len(rows) < 2:
        return {"segments": 0, "chapters": len(rows)}

    for r in rows:          # 重算前清旧段标记
        r.segment_no = None
        r.segment_summary = None
    db.commit()

    rate = rate or RateLimiter()
    seg_no = 1
    prev_tail = None
    n_batches = 0
    for i in range(0, len(rows), batch):
        batch_rows = rows[i:i + batch]
        numbered = "\n".join(f"第{r.chapter_no}章：{r.summary}" for r in batch_rows)
        raw = sf_chat(db, _segment_prompt(numbered, prev_tail),
                      max_tokens=2048, temperature=0.2, rate=rate)
        data = parse_json_loose(raw) or {}
        segs = data.get("segments") or []
        if not segs:
            logger.warning(f"[plot_import] 段切分批次未解析出 JSON（第 {batch_rows[0].chapter_no}"
                           f"~{batch_rows[-1].chapter_no} 章），整批回退为单段")
            segs = [{"chapters": [r.chapter_no for r in batch_rows],
                     "summary": "。".join(r.summary for r in batch_rows)[:200]}]
        covered: set[int] = set()
        for seg in segs:
            summary = (seg.get("summary") or "").strip()
            for no in seg.get("chapters") or []:
                hit = next((r for r in batch_rows if r.chapter_no == no), None)
                if hit is None or no in covered:
                    continue
                hit.segment_no = seg_no
                hit.segment_summary = summary
                covered.add(no)
            if covered and summary:
                prev_tail = summary
                seg_no += 1
        # LLM 漏标的章节 → 归入上一段（保证全覆盖）
        for r in batch_rows:
            if r.segment_no is None:
                r.segment_no = max(1, seg_no - 1)
        n_batches += 1
        if progress:
            progress(i + len(batch_rows), len(rows))
    db.commit()
    return {"segments": seg_no - 1, "chapters": len(rows), "batches": n_batches}


# ---------------------------------------------------------------------------
# 步骤 4：段分类（情节类型标签）
# ---------------------------------------------------------------------------
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
                max_tokens=32, temperature=0.2, rate=rate,
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
