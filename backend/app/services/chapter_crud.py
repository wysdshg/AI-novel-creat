"""章节服务（模块2/3 持久化层）。

当前仅实现「落库已生成/人工章节」。列表/详情接口在 routers/chapter.py 中按需扩展。
"""
import uuid

from sqlalchemy.orm import Session

from app.models.orm import ChapterORM, ProjectORM
from app.schemas.chapter import ChapterCreate


def _now():
    from datetime import datetime
    return datetime.utcnow()


def create_chapter(db: Session, project_id: str, data: ChapterCreate) -> ChapterORM:
    now = _now()
    o = ChapterORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        chapter_no=data.chapter_no,
        title=data.title,
        content=data.content,
        note=data.note,
        word_count=data.word_count,
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    # 同步更新作品章节计数
    proj = db.query(ProjectORM).filter_by(id=project_id).first()
    if proj:
        proj.chapter_count = (proj.chapter_count or 0) + 1
        proj.updated_at = now
    db.commit()
    db.refresh(o)
    return o


def get_chapter(db: Session, project_id: str, chapter_id: str) -> ChapterORM | None:
    return db.query(ChapterORM).filter_by(project_id=project_id, id=chapter_id).first()
