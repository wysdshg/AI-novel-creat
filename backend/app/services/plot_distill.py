"""情节模板凝练（Phase 7.1 步骤 5，2026-09-11）。

**上游**：`plot_import` 已把小说切成 章 → 情节段（beat）→ 故事弧（arc）。
**本模块**：把「相似的弧」凝练成**可复用模板**（`plot_templates`），供篇规划时借鉴。

流程（对应"AI 出候选组 + 用户确认"原则）：
  1. `cluster_arcs`  跨书聚类：用 bge-m3 向量算弧概括相似度，把"像同一个套路"的弧分到一组
     （= AI 候选组）；
  2. `distill_template`  对一组弧交给 DeepSeek 凝练成模板结构
     （phase → beat → **variants[各书的不同走法]**）；
  3. `distill_all` 串起来：聚类 → 逐组凝练 → 全部入库（`status="draft"` 待人工审核）。

**为什么 variants 是灵魂**：单个弧只能给"一种走法"，而模板的价值在于"这个节拍别人还有哪几种走法" ——
一组来自不同书的相似弧，恰好提供了同一节拍的多种处理方式（src 记来源书名）。

**人工确认**：本模块产出的一律是 `draft`；审核通过由人改 `status="reviewed"`（或删除）。
"""
import logging
from sqlalchemy.orm import Session

from app.models.orm import ChapterSummaryORM, PlotTemplateORM
from app.services import plot_template_crud as tpl_crud
from app.services import vector_index
from app.services.plot_import import DS_KEY_CONFIG, _ds_post, ds_key, parse_json_loose

logger = logging.getLogger(__name__)

# 弧聚类的相似度阈值（余弦，同一套路的不同书实现通常 0.80+；阈值取保守值防误并）
CLUSTER_THRESHOLD = 0.80


# ---------------------------------------------------------------------------
# 1. 收集弧明细（含 beat 级细节）
# ---------------------------------------------------------------------------
def collect_arcs(db: Session, book_names: list[str] | None = None) -> list[dict]:
    """收集弧及其 beat 明细。

    返回 [{book, arc_no, name, summary, beats: [{label, summary, chapters}]}]
    `book_names=None` 表示全部书。
    """
    q = db.query(ChapterSummaryORM).filter(ChapterSummaryORM.arc_no.isnot(None))
    if book_names:
        q = q.filter(ChapterSummaryORM.book_name.in_(book_names))
    rows = q.order_by(ChapterSummaryORM.book_name, ChapterSummaryORM.chapter_no).all()

    buckets: dict[tuple[str, int], dict] = {}
    for r in rows:
        key = (r.book_name, r.arc_no)
        b = buckets.setdefault(key, {
            "book": r.book_name,
            "arc_no": r.arc_no,
            "name": r.arc_name or f"弧{r.arc_no}",
            "summary": r.arc_summary or "",
            "segments": {},
        })
        if r.arc_name:
            b["name"] = r.arc_name
        if r.arc_summary:
            b["summary"] = r.arc_summary
        s = b["segments"].setdefault(r.segment_no, {
            "label": r.plot_label or "", "summary": r.segment_summary or "", "chapters": []})
        s["chapters"].append(r.chapter_no)
        if r.segment_summary:
            s["summary"] = r.segment_summary
        if r.plot_label:
            s["label"] = r.plot_label

    out = []
    for b in buckets.values():
        b["beats"] = [
            {"label": s["label"], "summary": s["summary"], "chapters": s["chapters"]}
            for _, s in sorted(b["segments"].items(), key=lambda kv: (kv[0] is None, kv[0] or 0))
        ]
        b.pop("segments")
        out.append(b)
    return out


# ---------------------------------------------------------------------------
# 2. 跨书聚类（AI 候选组）
# ---------------------------------------------------------------------------
def cluster_arcs(db: Session, arcs: list[dict] | None = None, *,
                 book_names: list[str] | None = None,
                 threshold: float = CLUSTER_THRESHOLD) -> list[dict]:
    """按弧概括的语义相似度聚类（贪心单遍，足够用）。

    返回候选组：[{arcs: [弧...], avg_sim, books: [书名...], suggest_name}]
    向量不可用时（未配检索 Key）→ 每个弧各成一组（**不硬报错**，退化为"每弧一模板"）。
    """
    arcs = arcs if arcs is not None else collect_arcs(db, book_names)
    if not arcs:
        return []

    vectors: list[list[float]] | None = None
    if vector_index.enabled(db):
        try:
            from app.services import embedding_client
            texts = [f"{a['name']}。{a['summary']}" for a in arcs]
            vectors = embedding_client.embed_texts(texts, db=db)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[plot_distill] 弧向量化失败，退化为每弧一组: {type(e).__name__}: {e}")
            vectors = None

    if not vectors:
        return [{"arcs": [a], "avg_sim": None, "books": [a["book"]], "suggest_name": a["name"]}
                for a in arcs]

    def cos(x, y):
        s = sum(i * j for i, j in zip(x, y))
        nx = sum(i * i for i in x) ** 0.5
        ny = sum(j * j for j in y) ** 0.5
        return s / (nx * ny) if nx and ny else 0.0

    groups: list[dict] = []
    for i, a in enumerate(arcs):
        placed = False
        for g in groups:
            sims = [cos(vectors[i], vectors[m]) for m in g["members"]]
            if max(sims) >= threshold:
                g["members"].append(i)
                g["sims"].extend(sims)
                placed = True
                break
        if not placed:
            groups.append({"members": [i], "sims": []})

    out = []
    for g in groups:
        members = [arcs[i] for i in g["members"]]
        books = sorted({m["book"] for m in members})
        out.append({
            "arcs": members,
            "avg_sim": round(sum(g["sims"]) / len(g["sims"]), 4) if g["sims"] else None,
            "books": books,
            "suggest_name": members[0]["name"] if len(members) == 1 else f"{members[0]['name']} 等",
        })
    out.sort(key=lambda x: -len(x["arcs"]))     # 大组优先
    return out


# ---------------------------------------------------------------------------
# 3. 凝练模板（一组弧 → plot_templates 结构）
# ---------------------------------------------------------------------------
def _distill_prompt(arcs: list[dict]) -> str:
    blocks = []
    for i, a in enumerate(arcs, 1):
        beats = "\n".join(
            f"  · [{b['label'] or '—'}] 第{b['chapters'][0]}~{b['chapters'][-1]}章：{b['summary']}"
            for b in a["beats"]
        )
        blocks.append(
            f"【弧 {i}】《{a['book']}》· {a['name']}\n弧概括：{a['summary']}\n节拍明细：\n{beats}"
        )
    return (
        f"下面是从小说中提取的 {len(arcs)} 个「故事弧」（一个弧 = 一个有完整冲突升级链的故事单元）。\n"
        "请把它们凝练成**一个可复用的情节模板**，供其他小说写作时借鉴。\n\n"
        "要求：\n"
        "1. `name`：4~8 字的套路名（如 学院大比 / 秘境寻宝 / 金手指觉醒 / 家族危机）；\n"
        "2. `logline`：一句话说清这个套路的核心张力（30 字内）；\n"
        "3. `genre_tags`：2~4 个题材或场景标签；\n"
        "4. `structure`：拆成 3~5 个 `phases`（阶段，如 开局/发展/高潮/收尾），每个 phase 下有若干 `beats`（节拍）；\n"
        "   每个 beat 用 `variants` 记录**各弧在这个节拍上的不同处理方式**"
        "（`src` 填来源书名，`how` 填 15~30 字的具体处理）—— 这是模板最有价值的部分；\n"
        "5. `pitfalls`：2~4 条这类套路的常见翻车点；\n"
        "6. `rhythm`：各阶段大致章数配比（如 \"2-3-3-2\"）。\n\n"
        "只输出 JSON（不要 markdown 代码块、不要任何额外说明）：\n"
        '{"name":"...","logline":"...","genre_tags":["..."],'
        '"structure":{"phases":[{"phase":"...","beats":[{"beat":"...",'
        '"variants":[{"src":"书名","how":"..."}]}]}]},'
        '"pitfalls":["..."],"rhythm":"..."}\n\n'
        + "\n\n".join(blocks)
    )


def distill_template(db: Session, arcs: list[dict], *, name_hint: str | None = None,
                     status: str = "draft", max_tokens: int = 4000):
    """把一组弧凝练成一个模板并入库（含 beat 级向量化）。返回 (ORM 对象, 原始输出)。

    幂等策略：**不覆盖已有模板** —— 每次调用都新建（draft），由人工在审核时决定留哪个。
    这样"重新凝练"不会毁掉此前的人工修改。
    """
    if not arcs:
        raise ValueError("arcs 为空，无法凝练")
    key = ds_key(db)
    if not key:
        raise RuntimeError(f"未配置 DeepSeek Key（app_configs.{DS_KEY_CONFIG}）")

    # LLM 偶发格式问题（如输出被截断）→ 重试一次，避免"偶尔一次坏输出就丢一组"
    raw, data = "", {}
    for attempt in range(2):
        raw = _ds_post(key, _distill_prompt(arcs), max_tokens=max_tokens)
        data = parse_json_loose(raw) or {}
        if data.get("name") and data.get("structure"):
            break
        logger.warning(f"[plot_distill] 凝练结果不完整（第 {attempt + 1}/2 次），"
                       f"raw 前 120 字: {raw[:120]!r}")
    if not data.get("name") or not data.get("structure"):
        return None, raw

    books = sorted({a["book"] for a in arcs})
    o = tpl_crud.create(db, {
        "name": name_hint or str(data.get("name")),
        "scale": "arc",
        "genre_tags": data.get("genre_tags") or [],
        "logline": data.get("logline"),
        "structure": data.get("structure") or {},
        "pitfalls": data.get("pitfalls") or [],
        "rhythm": data.get("rhythm"),
        "source_stats": {
            "books": len(books),
            "book_names": books,
            "arc_refs": [f"{a['book']}#{a['arc_no']}:{a['name']}" for a in arcs],
        },
        "status": status,
    })
    return o, raw


# ---------------------------------------------------------------------------
# 4. 一键流程：聚类 → 逐组凝练 → 入库
# ---------------------------------------------------------------------------
def distill_all(db: Session, *, book_names: list[str] | None = None,
                threshold: float = CLUSTER_THRESHOLD,
                min_arcs: int = 1, replace_drafts: bool = True) -> dict:
    """聚类全部弧 → 每组凝练一个模板 → 入库（draft）。

    `min_arcs` 可过滤太小的组（如只要"至少 2 个弧才算跨书套路"时设 2）。
    `replace_drafts=True`（默认）会**先清掉所有 draft 模板再重建** —— 避免反复跑时重复堆积；
    `status="reviewed"`（人工审核过）的模板**不受影响**。
    失败单组不中断整体（记录在结果里，含原始输出片段便于排查）。
    """
    if replace_drafts:
        n = db.query(PlotTemplateORM).filter_by(status="draft").delete(synchronize_session=False)
        db.commit()
        if n:
            logger.info(f"[plot_distill] 清理旧 draft 模板 {n} 个（reviewed 不动）")

    arcs = collect_arcs(db, book_names)
    groups = cluster_arcs(db, arcs, threshold=threshold)
    groups = [g for g in groups if len(g["arcs"]) >= max(1, min_arcs)]

    created, failed = [], []
    for g in groups:
        try:
            o, raw = distill_template(db, g["arcs"])
            if o is None:
                failed.append({"group": g["suggest_name"],
                               "reason": f"JSON 不完整；raw={(raw or '')[:100]!r}"})
                continue
            created.append({
                "id": o.id, "name": o.name, "books": g["books"],
                "arcs": len(g["arcs"]), "avg_sim": g["avg_sim"],
            })
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[plot_distill] 组「{g['suggest_name']}」凝练失败: "
                           f"{type(e).__name__}: {e}")
            failed.append({"group": g["suggest_name"], "reason": f"{type(e).__name__}: {e}"})
    return {"groups": len(groups), "created": len(created),
            "templates": created, "failed": failed}
