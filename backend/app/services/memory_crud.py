"""章级记忆 + 阶段摘要的持久化层。

分两层的理由很实在：写到第 50 章，如果注入的是 50 条章级记忆，
上下文会线性膨胀直到爆窗口。所以每满 N 章就把这批章级记忆再压成一条阶段摘要，
注入时用「若干条阶段摘要 + 最近 3 章章级记忆」——总量恒定。
"""
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.orm import ChapterMemoryORM, StageSummaryORM


def _now() -> datetime:
    return datetime.utcnow()


# ===========================================================================
# 章级记忆
# ===========================================================================

def upsert_chapter_memory(
    db: Session,
    project_id: str,
    chapter_id: str,
    data: dict,
) -> ChapterMemoryORM:
    """按 chapter_id 覆盖写。重生成同一章时，旧记忆必须被替换而不是并存——
    否则下一章会同时读到两个版本的剧情，人设直接分裂。
    """
    o = (
        db.query(ChapterMemoryORM)
        .filter_by(project_id=project_id, chapter_id=chapter_id)
        .first()
    )
    fields = {
        "article_id": data.get("article_id"),
        "chapter_no": int(data.get("chapter_no") or 0),
        "title": data.get("title"),
        "summary": (data.get("summary") or "").strip(),
        "ending_hook": (data.get("ending_hook") or "").strip() or None,
        "characters": data.get("characters") or [],
        "locations": data.get("locations") or [],
        "plot_points": data.get("plot_points") or [],
        "foreshadow_actions": data.get("foreshadow_actions") or [],
        "next_directions": data.get("next_directions") or [],
        "new_entities": data.get("new_entities") or [],
        "status": data.get("status") or "pending",
        "raw": data.get("raw"),
    }
    if o is None:
        o = ChapterMemoryORM(
            id=uuid.uuid4().hex,
            project_id=project_id,
            chapter_id=chapter_id,
            created_at=_now(),
            updated_at=_now(),
            **fields,
        )
        db.add(o)
    else:
        for k, v in fields.items():
            setattr(o, k, v)
        o.updated_at = _now()
    db.commit()
    db.refresh(o)
    return o


def get_chapter_memory(db: Session, project_id: str, chapter_id: str) -> ChapterMemoryORM | None:
    return (
        db.query(ChapterMemoryORM)
        .filter_by(project_id=project_id, chapter_id=chapter_id)
        .first()
    )


def list_chapter_memories(
    db: Session,
    project_id: str,
    article_id: str | None = None,
    limit: int | None = None,
) -> list[ChapterMemoryORM]:
    q = db.query(ChapterMemoryORM).filter_by(project_id=project_id)
    if article_id:
        q = q.filter(ChapterMemoryORM.article_id == article_id)
    q = q.order_by(ChapterMemoryORM.chapter_no.desc())
    if limit:
        q = q.limit(limit)
    return list(q.all())


def delete_chapter_memory(db: Session, project_id: str, chapter_id: str) -> bool:
    o = get_chapter_memory(db, project_id, chapter_id)
    if not o:
        return False
    db.delete(o)
    db.commit()
    return True


def set_status(db: Session, project_id: str, chapter_id: str, status: str) -> ChapterMemoryORM | None:
    o = get_chapter_memory(db, project_id, chapter_id)
    if not o:
        return None
    o.status = status
    o.updated_at = _now()
    db.commit()
    db.refresh(o)
    return o


# ===========================================================================
# 阶段摘要
# ===========================================================================

def upsert_stage_summary(
    db: Session,
    project_id: str,
    from_no: int,
    to_no: int,
    summary: str,
    key_events: list | None = None,
    open_threads: list | None = None,
    scope: str = "range",
    scope_id: str | None = None,
) -> StageSummaryORM:
    o = (
        db.query(StageSummaryORM)
        .filter_by(project_id=project_id, from_chapter_no=from_no, to_chapter_no=to_no)
        .first()
    )
    if o is None:
        o = StageSummaryORM(
            id=uuid.uuid4().hex,
            project_id=project_id,
            scope=scope,
            scope_id=scope_id,
            from_chapter_no=from_no,
            to_chapter_no=to_no,
            summary=summary,
            key_events=key_events or [],
            open_threads=open_threads or [],
            created_at=_now(),
            updated_at=_now(),
        )
        db.add(o)
    else:
        o.summary = summary
        o.key_events = key_events or []
        o.open_threads = open_threads or []
        o.scope = scope
        o.scope_id = scope_id
        o.updated_at = _now()
    db.commit()
    db.refresh(o)
    return o


def list_stage_summaries(db: Session, project_id: str) -> list[StageSummaryORM]:
    return list(
        db.query(StageSummaryORM)
        .filter_by(project_id=project_id)
        .order_by(StageSummaryORM.from_chapter_no)
        .all()
    )


def find_uncompressed_range(db: Session, project_id: str, every: int = 10) -> tuple[int, int] | None:
    """找出下一段该压缩的章号区间。

    规则：从「已压缩到的最大章号」往后数，凑满 every 章就返回一段。
    不足 every 章返回 None——半段压缩没意义，反而丢细节。
    """
    last = (
        db.query(StageSummaryORM)
        .filter_by(project_id=project_id)
        .order_by(StageSummaryORM.to_chapter_no.desc())
        .first()
    )
    start = (last.to_chapter_no + 1) if last else 1

    rows = (
        db.query(ChapterMemoryORM)
        .filter_by(project_id=project_id)
        .filter(ChapterMemoryORM.chapter_no >= start)
        .order_by(ChapterMemoryORM.chapter_no)
        .all()
    )
    if len(rows) < every:
        return None
    batch = rows[:every]
    return batch[0].chapter_no, batch[-1].chapter_no


def memory_to_dict(o: ChapterMemoryORM) -> dict:
    return {
        "id": o.id,
        "project_id": o.project_id,
        "chapter_id": o.chapter_id,
        "article_id": o.article_id,
        "chapter_no": o.chapter_no,
        "title": o.title,
        "summary": o.summary,
        "ending_hook": o.ending_hook,
        "characters": o.characters or [],
        "locations": o.locations or [],
        "plot_points": o.plot_points or [],
        "foreshadow_actions": o.foreshadow_actions or [],
        "next_directions": o.next_directions or [],
        "new_entities": o.new_entities or [],
        "status": o.status,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
    }


def stage_to_dict(o: StageSummaryORM) -> dict:
    return {
        "id": o.id,
        "project_id": o.project_id,
        "scope": o.scope,
        "scope_id": o.scope_id,
        "from_chapter_no": o.from_chapter_no,
        "to_chapter_no": o.to_chapter_no,
        "summary": o.summary,
        "key_events": o.key_events or [],
        "open_threads": o.open_threads or [],
        "created_at": o.created_at,
        "updated_at": o.updated_at,
    }
