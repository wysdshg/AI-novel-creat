"""参考文档 CRUD 服务（分作品隔离，project_id 过滤）。

提供 get_references_corpus() 供后续「章节生成」模块检索拼接，
将本作品全部参考文档文本拼为一段上下文，直接注入生成 Prompt。
"""
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.orm import ReferenceDocORM, SettingORM
from app.schemas.reference import ReferenceDocCreate, ReferenceDoc, ReferenceDocSummary

# 单次正文上限（字符），防止超大文档撑爆上下文；超过仅截断并标注。
MAX_CONTENT_CHARS = 200_000

# 全局共享参考文档（「参考资料」池）用特殊 project_id 存储，与「每本小说参考文档」共表隔离。
GLOBAL_PROJECT_ID = "__global__"

# 篇章参考文档固定文件名（每篇一个，AI 生成章后写入）
ARTICLE_REF_FILENAME = "篇章参考"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_summary(o: ReferenceDocORM) -> ReferenceDocSummary:
    return ReferenceDocSummary.model_validate(o)


def _to_full(o: ReferenceDocORM) -> ReferenceDoc:
    return ReferenceDoc.model_validate(o)


def list_references(db: Session, project_id: str) -> list[ReferenceDocSummary]:
    rows = (
        db.query(ReferenceDocORM)
        .filter_by(project_id=project_id)
        .order_by(ReferenceDocORM.created_at)
        .all()
    )
    return [_to_summary(r) for r in rows]


def auto_summary(content: str, limit: int = 220) -> str:
    """从正文首段抽一句话当摘要。

    没有 AI 也要有 summary——相关性打分和「其余文档一行式」注入都靠它。
    后续可由写后摄取用模型重写得更准，这里只保证不为空。
    """
    text = (content or "").strip()
    if not text:
        return ""
    for para in text.split("\n"):
        p = para.strip()
        # 跳过 Markdown 标题、分隔线这类没信息量的行
        if len(p) >= 10 and not p.startswith(("#", "---", "===", "|")):
            return p[:limit] + ("…" if len(p) > limit else "")
    return text[:limit]


def auto_tags(filename: str, content: str) -> list[str]:
    """从文件名切出检索标签。文件名往往就是最准的主题词（「太玄宗设定.md」）。"""
    stem = (filename or "").rsplit(".", 1)[0]
    raw = re.split(r"[\s_\-—·、,，。()（）\[\]【】]+", stem)
    tags = [t.strip() for t in raw if len(t.strip()) >= 2]
    seen, out = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:8]


def create_reference(db: Session, project_id: str, data: ReferenceDocCreate) -> ReferenceDoc:
    content = data.content_text or ""
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + "\n…(内容超出上限，已截断)"
    now = _now()
    o = ReferenceDocORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        filename=data.filename,
        content_type=data.content_type or "text/plain",
        size=data.size or len(content.encode("utf-8")),
        content_text=content,
        summary=auto_summary(content),
        tags=auto_tags(data.filename, content),
        source="global" if project_id == GLOBAL_PROJECT_ID else "upload",
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_full(o)


def get_reference(db: Session, project_id: str, doc_id: str) -> ReferenceDoc | None:
    o = db.query(ReferenceDocORM).filter_by(project_id=project_id, id=doc_id).first()
    return _to_full(o) if o else None


def delete_reference(db: Session, project_id: str, doc_id: str) -> bool:
    o = db.query(ReferenceDocORM).filter_by(project_id=project_id, id=doc_id).first()
    if o is None:
        return False
    db.delete(o)
    db.commit()
    return True


def get_references_corpus(db: Session, project_id: str, article_id: str | None = None, limit: int = 10) -> str:
    """检索本作品参考文档，拼为一段上下文文本，供 AI 生成时读取。

    - 默认：本作品（project_id）维度全部参考文档。
    - article_id 给定：额外纳入该篇维度的「篇章参考文档」（每篇一个，AI 写入）。
    limit: 最多拼接的文档数（按上传顺序）。返回空串表示无参考文档。
    """
    q = db.query(ReferenceDocORM).filter_by(project_id=project_id)
    if article_id is not None:
        # 同作品的篇维度文档也一并纳入（project_id 必匹配，再按 article_id 过滤）
        q = q.filter(
            (ReferenceDocORM.article_id.is_(None)) | (ReferenceDocORM.article_id == article_id)
        )
    rows = q.order_by(ReferenceDocORM.created_at).limit(limit).all()
    if not rows:
        return ""
    blocks = []
    for i, o in enumerate(rows, 1):
        scope = "（篇章参考）" if o.article_id else ""
        blocks.append(f"【参考文档 {i}{scope}：{o.filename}】\n{o.content_text}\n")
    return "\n\n".join(blocks)


# ----------------------------------------------------------------------------
# 按需加载（retrieve-on-demand）目录：给 AI 一份「文件清单」，由它决定加载哪些。
# 这样避免把所有参考一股脑塞进上下文；仅选中项才取正文注入。
# ----------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """轻量 token 估算（零依赖）。

    与 budget.py 口径一致：中文 1 token ≈ 1.5 字符。用于目录里展示「这份文件多大」，
    帮助 AI 决策是否加载；后端预算系统仍按字符算，不受此影响。
    """
    chars = len(text or "")
    return round(chars / 1.5)


def build_catalog(
    db: Session,
    project_id: str,
    article_id: str | None = None,
    include_global: bool = False,
) -> list:
    """构造参考文件目录（给 AI 看的清单），不含正文。

    - 默认：本小说（project_id）维度参考文档（不含篇章维度，除非给了 article_id）。
    - include_global=True：并上全局池（GLOBAL_PROJECT_ID）资料，允许 AI 在线拉取全局参考。
    - locked：source=='auto' 或 article_id 非空 的文档（篇章摘要），必备上下文，AI 不可跳过。
    - 排序：locked 置顶；其余按相关性（score_reference）降序，让最相关的排前面，
      减少 AI 在长目录里瞎挑。

    返回 list[ReferenceCatalogItem]。
    """
    from app.schemas.reference import ReferenceCatalogItem

    rows: list[ReferenceDocORM] = []
    q = db.query(ReferenceDocORM).filter_by(project_id=project_id)
    if article_id is not None:
        q = q.filter(
            (ReferenceDocORM.article_id.is_(None)) | (ReferenceDocORM.article_id == article_id)
        )
    else:
        q = q.filter(ReferenceDocORM.article_id.is_(None))
    rows.extend(q.all())

    if include_global and project_id != GLOBAL_PROJECT_ID:
        grow = (
            db.query(ReferenceDocORM)
            .filter_by(project_id=GLOBAL_PROJECT_ID)
            .filter(ReferenceDocORM.article_id.is_(None))
            .all()
        )
        rows.extend(grow)

    items = []
    for o in rows:
        content = o.content_text or ""
        locked = (o.source or "") == "auto" or bool(o.article_id)
        items.append(
            ReferenceCatalogItem(
                id=o.id,
                filename=o.filename,
                summary=o.summary,
                tags=list(o.tags or []),
                source=o.source or "upload",
                size=o.size or len(content.encode("utf-8")),
                content_chars=len(content),
                token_est=estimate_tokens(content),
                article_id=o.article_id,
                locked=locked,
            )
        )

    # locked 置顶；其余按文件名稳定排序（相关性排序需 query_text，目录阶段无 query，保持简单）
    items.sort(key=lambda it: (not it.locked, it.filename))
    return items


def format_catalog_prompt(items: list, include_global: bool = False) -> str:
    """把目录渲染成一段系统提示词前缀，供 AI 决策要加载哪些文件。

    稳定前缀（不随每轮对话变化，除非目录本身变）→ 配合 Ollama cache_prompt 缓存，
    后续轮次前缀 KV 复用，前缀重传成本≈0。
    """
    if not items:
        return ""

    lines = ["", "## 可用参考文件目录（按需加载）",
             "下面是当前作品可参考的资料清单。除非你确定需要其中某份资料来准确回答，"
             "否则不要加载——直接作答即可。\n"
             "需要时在正式回答前先输出一行加载指令（**支持一次请求多个文件，用逗号分隔**）：\n"
             "  LOAD_REFS:<id1>,<id2>,<id3>\n"
             "【重要】如果你的回答需要用到多份资料（例如同时涉及官制和俸禄），"
             "必须把所有相关文件的 id 写在同一行里一次性请求，不要只请求一个然后靠猜。"
             "系统会把所有请求的正文一并注入后再让你作答。带 [必备] 的项已自动加载，无需你请求。", ""]
    for it in items:
        tag = " [必备]" if it.locked else ""
        summary = (it.summary or "").strip().replace("\n", " ")
        tags = " ".join(f"#{t}" for t in it.tags[:6])
        lines.append(
            f"- id={it.id} | {it.filename}{tag} | ~{it.token_est} tokens | {it.source}"
        )
        if summary:
            lines.append(f"    摘要：{summary[:80]}")
        if tags:
            lines.append(f"    标签：{tags}")
    if include_global:
        lines.append("")
        lines.append("（注：以上含全局参考资料池，可直接加载，无需先导入本作品。）")
    lines.append("")
    return "\n".join(lines)


_LOAD_REFS_RE = re.compile(r"LOAD_REFS:\s*([0-9a-fA-F,\s]+)", re.IGNORECASE)


def parse_load_refs(text: str) -> list[str] | None:
    """从模型首轮回复里解析 LOAD_REFS 指令。

    返回选中的 id 列表；若没有该指令则返回 None（表示模型直接作答、无需额外加载）。
    容忍模型夹带少量其它文字——取第一个匹配即可。
    """
    if not text:
        return None
    m = _LOAD_REFS_RE.search(text)
    if not m:
        return None
    ids = [x.strip() for x in m.group(1).split(",") if x.strip()]
    return ids or None


def fetch_refs_by_ids(db: Session, ids: list[str]) -> list[tuple[str, str]]:
    """按 id 批量取参考文档正文（id 在整张表唯一，不限 project）。

    返回 [(filename, content_text), ...]，按传入 id 顺序。用于 retrieve_refs 语义：
    一次往返取回全部选中正文，注入上下文。
    """
    if not ids:
        return []
    rows = db.query(ReferenceDocORM).filter(ReferenceDocORM.id.in_(ids)).all()
    by_id = {o.id: o for o in rows}
    out = []
    for i in ids:
        o = by_id.get(i)
        if o:
            out.append((o.filename, o.content_text or ""))
    return out


# ----------------------------------------------------------------------------
# 设定库按需加载（B 方案）：与参考文档的 LOAD_REFS 平行。
# 设定库（SettingORM）与参考文档（ReferenceDocORM）用不同标记 + 不同 id 空间，
# 避免 id 碰撞；两者可在同一模型首轮文本里同时出现，Pass1 一并解析。
# ----------------------------------------------------------------------------

_LOAD_SETTING_RE = re.compile(r"LOAD_SETTING:\s*([0-9a-fA-F,\s]+)", re.IGNORECASE)


def parse_load_setting(text: str) -> list[str] | None:
    """从模型首轮回复里解析 LOAD_SETTING 指令（设定库按需加载）。

    返回选中的设定 id 列表；若没有该指令则返回 None（表示模型直接作答、无需加载设定）。
    容忍模型夹带少量其它文字——取第一个匹配即可。
    """
    if not text:
        return None
    m = _LOAD_SETTING_RE.search(text)
    if not m:
        return None
    ids = [x.strip() for x in m.group(1).split(",") if x.strip()]
    return ids or None


def fetch_settings_by_ids(db: Session, ids: list[str]) -> list[tuple[str, str]]:
    """按 id 批量取设定库详情（SettingORM.id，整表唯一，不限 project）。

    返回 [(name, detail_text), ...]，按传入 id 顺序。detail 含层级阶梯 + 完整描述，
    供 LOAD_SETTING 语义：一次往返取回全部选中设定，注入上下文。
    """
    if not ids:
        return []
    rows = db.query(SettingORM).filter(SettingORM.id.in_(ids)).all()
    by_id = {o.id: o for o in rows}
    out = []
    for i in ids:
        o = by_id.get(i)
        if o:
            parts = [f"【设定：{o.name}（{o.category or '其它'}）】"]
            if o.levels:
                parts.append("层级阶梯：" + "→".join(str(x) for x in o.levels))
            desc = (o.description or "").strip()
            if desc:
                parts.append(desc)
            out.append((o.name, "\n".join(parts) + "\n"))
    return out


def import_global_references(db: Session, project_id: str, doc_ids: list[str]) -> int:
    """将选中的「全局参考资料」复制进指定小说（成为该小说的参考文档）。

    返回实际复制的条数。全局池本身不受影响。
    """
    if not doc_ids:
        return 0
    src = (
        db.query(ReferenceDocORM)
        .filter_by(project_id=GLOBAL_PROJECT_ID)
        .filter(ReferenceDocORM.id.in_(doc_ids))
        .all()
    )
    now = _now()
    count = 0
    for o in src:
        content = o.content_text or ""
        if len(content) > MAX_CONTENT_CHARS:
            content = content[:MAX_CONTENT_CHARS] + "\n…(内容超出上限，已截断)"
        db.add(
            ReferenceDocORM(
                id=uuid.uuid4().hex,
                project_id=project_id,
                article_id=None,  # 进入小说维度，非篇章维度
                filename=o.filename,
                content_type=o.content_type or "text/plain",
                size=o.size or len(content.encode("utf-8")),
                content_text=content,
                summary=o.summary or auto_summary(content),
                tags=list(o.tags or []) or auto_tags(o.filename, content),
                source="global",
                created_at=now,
                updated_at=now,
            )
        )
        count += 1
    db.commit()
    return count


# 章节段落分隔标记：用它定位/替换单章内容，实现「追加而不覆盖、重生成而不重复」
_CH_MARK = "<!-- ch:{no} -->"
_CH_MARK_RE = re.compile(r"<!-- ch:(\d+) -->")


def append_article_digest(
    db: Session,
    project_id: str,
    article_id: str,
    chapter_no: int,
    title: str | None,
    digest: str,
) -> None:
    """把一章的**摘要**追加进「篇章参考文档」。

    这里修掉了一个会静默丢数据的 bug：原实现每生成一章就用本章全文
    整体覆盖这份文档，于是写第 2 章时第 1 章的内容被冲掉，
    所谓「篇章参考」永远只剩最后一章。

    现在改为：
    - 按 `<!-- ch:N -->` 标记分段，每章一段，**追加**不覆盖；
    - 同一章重新生成时只替换它自己那一段，不会产生重复段；
    - 存的是摘要不是全文——全文已经在 chapters 表里，
      参考文档存全文既撑爆上下文又没有额外价值。
    """
    digest = (digest or "").strip()
    if not digest:
        return
    now = _now()
    header = f"{_CH_MARK.format(no=chapter_no)}\n## 第{chapter_no}章 {title or ''}".rstrip()
    section = f"{header}\n{digest}"

    existing = (
        db.query(ReferenceDocORM)
        .filter_by(project_id=project_id, article_id=article_id, filename=ARTICLE_REF_FILENAME)
        .first()
    )

    if existing is None:
        body = f"本篇已完成章节的剧情摘要，按章号排列。\n\n{section}"
        db.add(ReferenceDocORM(
            id=uuid.uuid4().hex,
            project_id=project_id,
            article_id=article_id,
            filename=ARTICLE_REF_FILENAME,
            content_type="text/plain",
            size=len(body.encode("utf-8")),
            content_text=body,
            summary="本篇已写章节的剧情摘要索引",
            tags=["篇章摘要", "剧情回顾"],
            source="auto",
            created_at=now,
            updated_at=now,
        ))
        db.commit()
        return

    old = existing.content_text or ""
    marker = _CH_MARK.format(no=chapter_no)
    if marker in old:
        # 该章已有段落（重新生成）：只替换它，直到下一个章节标记为止
        start = old.index(marker)
        rest = old[start + len(marker):]
        nxt = _CH_MARK_RE.search(rest)
        end = start + len(marker) + (nxt.start() if nxt else len(rest))
        new_body = old[:start] + section + ("\n\n" if nxt else "") + old[end:]
    else:
        new_body = old.rstrip() + "\n\n" + section

    if len(new_body) > MAX_CONTENT_CHARS:
        # 超限时从最早的章节开始丢，保住最近的剧情
        marks = list(_CH_MARK_RE.finditer(new_body))
        while len(new_body) > MAX_CONTENT_CHARS and len(marks) > 1:
            new_body = new_body[:marks[0].start()] + new_body[marks[1].start():]
            marks = list(_CH_MARK_RE.finditer(new_body))

    existing.content_text = new_body
    existing.size = len(new_body.encode("utf-8"))
    existing.source = "auto"
    existing.updated_at = now
    db.commit()


def upsert_article_reference(db: Session, project_id: str, article_id: str, content: str) -> None:
    """兼容旧签名。内部已改为追加式摘要，不再整体覆盖。

    没有章号信息时按「未编号」段落追加，避免老调用点静默丢数据。
    """
    append_article_digest(db, project_id, article_id, 0, "未编号", (content or "")[:1500])


# ===========================================================================
# 相关性筛选（需求 2-B：生成时只挑真正用得上的资料）
# ===========================================================================

def score_reference(doc: ReferenceDocORM, query_text: str, entity_names: set[str]) -> float:
    """给文档打相关性分。

    不用向量检索的原因：本地只有 chat 模型没有 embedding 模型，
    而且小说的专有名词（自造人名/门派名）恰恰是关键词匹配最擅长、
    通用嵌入模型最不擅长的部分。

    打分维度：
      标签命中     ×5  —— 标签是人工/半自动标注的主题词，最准
      文件名命中   ×4
      摘要重合     ×2
      实体名出现   ×1.5（上限 5 次）—— 文档里讲到了本章要出场的人/地
    """
    q = query_text or ""
    score = 0.0

    for tag in (doc.tags or []):
        t = str(tag).strip()
        if len(t) >= 2 and t in q:
            score += 5.0

    stem = (doc.filename or "").rsplit(".", 1)[0].strip()
    if len(stem) >= 2 and stem in q:
        score += 4.0

    summary = (doc.summary or "")[:300]
    if summary:
        # 摘要里的 2-gram 有多少出现在 query 里——粗糙但对中文很有效，且零依赖
        grams = {summary[i:i + 2] for i in range(len(summary) - 1)}
        if grams:
            hit = sum(1 for g in grams if g in q)
            score += min(hit / len(grams) * 6.0, 3.0)

    body = doc.content_text or ""
    if body and entity_names:
        for name in entity_names:
            c = body.count(name)
            if c:
                score += min(c, 5) * 1.5

    return round(score, 2)


def pick_relevant(
    db: Session,
    project_id: str,
    article_id: str | None,
    query_text: str,
    entity_names: set[str] | None = None,
    top_k: int = 4,
    per_doc_chars: int = 3000,
) -> tuple[str, list[dict]]:
    """挑出与本章相关的参考文档，拼成上下文。

    返回 (拼接文本, 命中明细)。明细供前端展示「本章参考了哪几份资料」。

    篇章摘要（source=auto）永远置顶且不参与竞争——那是本篇已发生的剧情，
    属于必备上下文，不是可选参考。
    """
    entity_names = entity_names or set()
    try:
        q = db.query(ReferenceDocORM).filter_by(project_id=project_id)
        if article_id is not None:
            q = q.filter(
                (ReferenceDocORM.article_id.is_(None))
                | (ReferenceDocORM.article_id == article_id)
            )
        else:
            q = q.filter(ReferenceDocORM.article_id.is_(None))
        rows = q.all()
    except Exception as e:  # noqa: BLE001
        print(f"[reference_crud.pick_relevant] 查询失败: {e}")
        return "", []

    if not rows:
        return "", []

    must = [r for r in rows if (r.source or "") == "auto" or r.article_id]
    optional = [r for r in rows if r not in must]

    scored = [(score_reference(d, query_text, entity_names), d) for d in optional]
    scored.sort(key=lambda x: (-x[0], x[1].created_at or _now()))
    picked = [d for s, d in scored[:max(0, top_k)] if s > 0]

    # 一份都没命中时，退回最早上传的一份保底——总比完全没有世界观参考强
    if not picked and optional:
        picked = [optional[0]]

    detail: list[dict] = []
    blocks: list[str] = []

    for d in must:
        text = (d.content_text or "").strip()
        if not text:
            continue
        blocks.append(f"【本篇已写剧情摘要】\n{text[:per_doc_chars * 2]}")
        detail.append({"id": d.id, "filename": d.filename, "score": None, "reason": "本篇剧情摘要（必备）"})

    score_map = {d.id: s for s, d in scored}
    for d in picked:
        text = (d.content_text or "").strip()
        if not text:
            continue
        clipped = text[:per_doc_chars]
        if len(text) > per_doc_chars:
            clipped += f"\n…（全文 {len(text)} 字，此处截取前 {per_doc_chars} 字）"
        blocks.append(f"【参考资料：{d.filename}】\n{clipped}")
        detail.append({
            "id": d.id, "filename": d.filename,
            "score": score_map.get(d.id, 0),
            "reason": "关键词相关性命中",
        })

    # 未入选的只留一行索引，让模型知道「还有这些资料存在」
    rest = [d for d in optional if d not in picked]
    if rest:
        lines = [f"· {d.filename}：{(d.summary or '')[:60]}" for d in rest[:12]]
        blocks.append("【其余可用资料（本章未展开，如需要请在要点中指明）】\n" + "\n".join(lines))

    return "\n\n".join(blocks), detail


def recommend_global_references(
    db: Session, project_id: str, top_k: int = 8
) -> list[dict]:
    """需求 2-A：从全局资料池里推荐值得导入本作品的资料。

    用作品名/题材/梗概 + 已有角色势力地点名当查询，对全局池打分排序。
    只给建议，导入与否由作者点确认——这是「AI 判断哪些资料需要借鉴」的入口。
    """
    from app.models.orm import ProjectORM, CharacterORM, FactionORM, LocationORM

    try:
        p = db.query(ProjectORM).filter_by(id=project_id).first()
        query_bits = []
        if p:
            query_bits += [p.name or "", p.genre or "", p.summary or ""]
        names: set[str] = set()
        for model in (CharacterORM, FactionORM, LocationORM):
            for r in db.query(model).filter_by(project_id=project_id).all():
                if r.name:
                    names.add(r.name)
        query_bits += list(names)
        query_text = " ".join(query_bits)

        existing_names = {
            r.filename for r in db.query(ReferenceDocORM).filter_by(project_id=project_id).all()
        }
        pool = db.query(ReferenceDocORM).filter_by(project_id=GLOBAL_PROJECT_ID).all()
    except Exception as e:  # noqa: BLE001
        print(f"[reference_crud.recommend_global_references] 失败: {e}")
        return []

    out = []
    for d in pool:
        if d.filename in existing_names:
            continue  # 已导入过的不再推荐
        s = score_reference(d, query_text, names)
        out.append({
            "id": d.id,
            "filename": d.filename,
            "summary": (d.summary or "")[:120],
            "tags": d.tags or [],
            "size": d.size,
            "score": s,
            "recommended": s >= 4.0,
        })
    out.sort(key=lambda x: -x["score"])
    return out[:max(1, top_k)]
