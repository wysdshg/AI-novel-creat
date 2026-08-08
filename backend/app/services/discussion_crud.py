"""剧情商讨缓存持久化层（模块3 / 需求 6）。

discussion_messages 表按 project_id 隔离存储商讨草稿；
archived_chapter_id 非空 = 已归档到某章节（保留历史，不再出现在「当前缓存」中）。
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.orm import DiscussionMessageORM, ChapterORM


def _now() -> datetime:
    return datetime.utcnow()


def add_message(
    db: Session,
    project_id: str,
    role: str,
    content: str,
    thinking: Optional[str] = None,
    meta: Optional[dict] = None,
) -> DiscussionMessageORM:
    """追加一条商讨消息（role: user / assistant）。"""
    o = DiscussionMessageORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        role=role,
        content=content,
        thinking=thinking,
        meta=meta,
        archived_chapter_id=None,
        created_at=_now(),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def list_messages(db: Session, project_id: str, include_archived: bool = False) -> list:
    """返回商讨消息，按时间升序。默认只返回「当前缓存」（未归档）。"""
    q = db.query(DiscussionMessageORM).filter_by(project_id=project_id)
    if not include_archived:
        q = q.filter(DiscussionMessageORM.archived_chapter_id.is_(None))
    return q.order_by(DiscussionMessageORM.created_at.asc()).all()


def count_current(db: Session, project_id: str) -> int:
    return (
        db.query(DiscussionMessageORM)
        .filter_by(project_id=project_id, archived_chapter_id=None)
        .count()
    )


def clear_messages(db: Session, project_id: str) -> int:
    """清空「当前缓存」（仅未归档消息）。返回删除条数。"""
    n = (
        db.query(DiscussionMessageORM)
        .filter_by(project_id=project_id, archived_chapter_id=None)
        .delete()
    )
    db.commit()
    return n


def archive_to_chapter(db: Session, project_id: str, chapter_id: str) -> dict:
    """将当前商讨草稿追加为章节备注，并标记消息为已归档。

    保留消息历史（仅从「当前缓存」移出），并在章节 note 中追加可读的商讨记录。
    """
    msgs = list_messages(db, project_id, include_archived=False)
    if not msgs:
        return {"archived_count": 0, "chapter_id": chapter_id}

    lines = []
    for m in msgs:
        role_label = "作者" if m.role == "user" else "AI"
        lines.append(f"【{role_label}】{m.content}")
    block = "\n\n".join(lines)

    chapter = db.query(ChapterORM).filter_by(id=chapter_id, project_id=project_id).first()
    if chapter is not None:
        chapter.note = (chapter.note or "") + f"\n\n【商讨记录】\n{block}"
        chapter.updated_at = _now()

    for m in msgs:
        m.archived_chapter_id = chapter_id
    db.commit()
    return {"archived_count": len(msgs), "chapter_id": chapter_id}
