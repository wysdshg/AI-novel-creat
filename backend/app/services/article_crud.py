"""篇（article）CRUD 服务。"""
import uuid

from sqlalchemy.orm import Session

from app.models.orm import ArticleORM, VolumeORM
from app.schemas.article import ArticleCreate, ArticleUpdate


def _now():
    from datetime import datetime
    return datetime.utcnow()


def create_article(db: Session, project_id: str, data: ArticleCreate) -> ArticleORM | None:
    """创建篇：必须校验所属卷存在且属于同一 project。"""
    vol = db.query(VolumeORM).filter_by(id=data.volume_id, project_id=project_id).first()
    if not vol:
        return None
    now = _now()
    o = ArticleORM(
        id=uuid.uuid4().hex,
        volume_id=data.volume_id,
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


def list_articles(db: Session, project_id: str, volume_id: str | None = None) -> list[ArticleORM]:
    """列篇：默认按 project 列出；如有 volume_id 则仅列出该卷下的篇。"""
    q = db.query(ArticleORM).filter_by(project_id=project_id)
    if volume_id:
        q = q.filter_by(volume_id=volume_id)
    return q.order_by(ArticleORM.sort_order.asc(), ArticleORM.created_at.asc()).all()


def get_article(db: Session, project_id: str, article_id: str) -> ArticleORM | None:
    return db.query(ArticleORM).filter_by(project_id=project_id, id=article_id).first()


def update_article(db: Session, project_id: str, article_id: str, data: ArticleUpdate) -> ArticleORM | None:
    o = get_article(db, project_id, article_id)
    if not o:
        return None
    payload = data.model_dump(exclude_unset=True)
    # 若要换卷，必须校验目标卷存在且属于同一 project
    if "volume_id" in payload and payload["volume_id"] and payload["volume_id"] != o.volume_id:
        vol = db.query(VolumeORM).filter_by(id=payload["volume_id"], project_id=project_id).first()
        if not vol:
            return None
    for k, v in payload.items():
        setattr(o, k, v)
    o.updated_at = _now()
    db.commit()
    db.refresh(o)
    return o


def delete_article(db: Session, project_id: str, article_id: str) -> bool:
    o = get_article(db, project_id, article_id)
    if not o:
        return False
    db.delete(o)
    db.commit()
    return True
