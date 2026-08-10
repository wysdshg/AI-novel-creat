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
    chapter_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> DiscussionMessageORM:
    """追加一条商讨消息（role: user / assistant）。

    线程归属（互斥，优先级从高到低）：
    - conversation_id 非空 → 该消息属于某个「会话」线程（独立记忆）。
    - 否则 chapter_id 非空 → 属于某个「章」的线程。
    - 否则 → 小说级默认线程（chapter_id IS NULL 且 conversation_id IS NULL）。
    """
    o = DiscussionMessageORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        chapter_id=chapter_id,
        conversation_id=conversation_id,
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


def list_messages(
    db: Session,
    project_id: str,
    chapter_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    include_archived: bool = False,
) -> list:
    """返回商讨消息，按时间升序。默认只返回「当前缓存」（未归档）。

    线程优先级：conversation_id > chapter_id > 小说级默认线程。
    - conversation_id 给定 → 返回该会话线程。
    - 否则 chapter_id 给定 → 返回该章线程。
    - 否则 → 返回小说级默认线程（两者均为 NULL）。
    """
    q = db.query(DiscussionMessageORM).filter_by(project_id=project_id)
    if conversation_id is not None:
        q = q.filter_by(conversation_id=conversation_id)
    elif chapter_id is not None:
        q = q.filter_by(chapter_id=chapter_id)
    else:
        q = q.filter(
            DiscussionMessageORM.chapter_id.is_(None),
            DiscussionMessageORM.conversation_id.is_(None),
        )
    if not include_archived:
        q = q.filter(DiscussionMessageORM.archived_chapter_id.is_(None))
    return q.order_by(DiscussionMessageORM.created_at.asc()).all()


def count_current(db: Session, project_id: str) -> int:
    return (
        db.query(DiscussionMessageORM)
        .filter_by(project_id=project_id, archived_chapter_id=None)
        .count()
    )


def clear_messages(
    db: Session,
    project_id: str,
    chapter_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> int:
    """清空「当前缓存」。

    线程优先级同 list_messages：conversation_id > chapter_id > 小说级默认线程。
    返回删除条数。
    """
    q = db.query(DiscussionMessageORM).filter_by(project_id=project_id)
    if conversation_id is not None:
        q = q.filter_by(conversation_id=conversation_id)
    elif chapter_id is not None:
        q = q.filter_by(chapter_id=chapter_id)
    else:
        q = q.filter(
            DiscussionMessageORM.chapter_id.is_(None),
            DiscussionMessageORM.conversation_id.is_(None),
        )
    q = q.filter(DiscussionMessageORM.archived_chapter_id.is_(None))
    n = q.delete()
    db.commit()
    return n


def archive_to_chapter(
    db: Session,
    project_id: str,
    chapter_id: str,
    conversation_id: Optional[str] = None,
) -> dict:
    """将当前商讨草稿归档为指定章节备注，并标记消息为已归档。

    源线程：conversation_id 给定则取该会话线程；否则取小说级默认线程
    （chapter_id=None 且 conversation_id=None）。
    保留消息历史（仅从「当前缓存」移出），并在章节 note 中追加可读的商讨记录。
    """
    msgs = list_messages(db, project_id, chapter_id=None, conversation_id=conversation_id, include_archived=False)
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
