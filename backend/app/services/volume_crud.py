"""卷（volume）CRUD 服务。"""
import uuid

from sqlalchemy.orm import Session

from app.models.orm import VolumeORM, ArticleORM, ChapterORM
from app.schemas.volume import VolumeCreate, VolumeUpdate


def _now():
    from datetime import datetime
    return datetime.utcnow()


def create_volume(db: Session, project_id: str, data: VolumeCreate) -> VolumeORM:
    now = _now()
    o = VolumeORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        name=data.name,
        summary=data.summary,
        sort_order=data.sort_order,
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def list_volumes(db: Session, project_id: str) -> list[VolumeORM]:
    return db.query(VolumeORM).filter_by(project_id=project_id) \
        .order_by(VolumeORM.sort_order.asc(), VolumeORM.created_at.asc()).all()


def get_volume(db: Session, project_id: str, volume_id: str) -> VolumeORM | None:
    return db.query(VolumeORM).filter_by(project_id=project_id, id=volume_id).first()


def update_volume(db: Session, project_id: str, volume_id: str, data: VolumeUpdate) -> VolumeORM | None:
    o = get_volume(db, project_id, volume_id)
    if not o:
        return None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(o, k, v)
    o.updated_at = _now()
    db.commit()
    db.refresh(o)
    return o


def delete_volume(db: Session, project_id: str, volume_id: str) -> bool:
    o = get_volume(db, project_id, volume_id)
    if not o:
        return False
    # 级联删除该卷下所有篇及其章节，避免孤儿数据
    article_ids = [r[0] for r in db.query(ArticleORM.id).filter_by(volume_id=volume_id).all()]
    if article_ids:
        db.query(ChapterORM).filter(ChapterORM.article_id.in_(article_ids)).delete()
        db.query(ArticleORM).filter(ArticleORM.id.in_(article_ids)).delete()
    db.delete(o)
    db.commit()
    return True
