"""章节服务（4 级结构：小说 → 卷 → 篇 → 章）中的「章」持久化层。

完整 CRUD：create / list（按 project or article）/ get / update / delete。
所有变更同步更新 ProjectORM.chapter_count（按需）。
"""
import uuid

from sqlalchemy.orm import Session

from app.models.orm import ChapterORM, ProjectORM
from app.schemas.chapter import ChapterCreate, ChapterUpdate
from app.services.discussion_crud import clear_messages


def _now():
    from datetime import datetime
    return datetime.utcnow()


def create_chapter(db: Session, project_id: str, data: ChapterCreate) -> ChapterORM:
    now = _now()
    o = ChapterORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        article_id=data.article_id,
        chapter_no=data.chapter_no,
        title=data.title,
        content=data.content,
        note=data.note,
        word_count=data.word_count,
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    proj = db.query(ProjectORM).filter_by(id=project_id).first()
    if proj:
        proj.chapter_count = (proj.chapter_count or 0) + 1
        proj.updated_at = now
    db.commit()
    db.refresh(o)
    return o


def get_chapter(db: Session, project_id: str, chapter_id: str) -> ChapterORM | None:
    return db.query(ChapterORM).filter_by(project_id=project_id, id=chapter_id).first()


def list_chapters(db: Session, project_id: str, article_id: str | None = None) -> list[ChapterORM]:
    """列章：默认按 project 列出；如有 article_id 则仅列出该篇下的章。"""
    q = db.query(ChapterORM).filter_by(project_id=project_id)
    if article_id:
        q = q.filter_by(article_id=article_id)
    return q.order_by(ChapterORM.chapter_no.asc(), ChapterORM.created_at.asc()).all()


def update_chapter(db: Session, project_id: str, chapter_id: str, data: ChapterUpdate) -> ChapterORM | None:
    o = get_chapter(db, project_id, chapter_id)
    if not o:
        return None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(o, k, v)
    o.updated_at = _now()
    db.commit()
    db.refresh(o)
    return o


def delete_chapter(db: Session, project_id: str, chapter_id: str) -> bool:
    o = get_chapter(db, project_id, chapter_id)
    if not o:
        return False
    # 级联清理该章节的商讨线程（避免孤儿对话残留）
    clear_messages(db, project_id, chapter_id=chapter_id)
    db.delete(o)
    proj = db.query(ProjectORM).filter_by(id=project_id).first()
    if proj and (proj.chapter_count or 0) > 0:
        proj.chapter_count -= 1
    db.commit()
    return True
