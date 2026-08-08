"""关系网 CRUD 服务（模块1：分作品资料库）。

分作品隔离通过 project_id 实现：所有查询/写入均按 project_id 过滤。
关系是有向边：subject_id -> object_id，携带 relation_type / strength / note。
此前 routers/database.py 中 relations 端点是占位桩，这里落地真实持久化。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.orm import RelationORM
from app.schemas.database import Relation, RelationCreate, RelationUpdate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_schema(o: RelationORM) -> Relation:
    return Relation(
        id=o.id,
        subject_id=o.subject_id,
        object_id=o.object_id,
        relation_type=o.relation_type,
        strength=o.strength,
        note=o.note,
    )


def list_relations(
    db: Session, project_id: str, character_id: str | None = None
) -> list[Relation]:
    q = db.query(RelationORM).filter_by(project_id=project_id)
    if character_id:
        q = q.filter(
            (RelationORM.subject_id == character_id)
            | (RelationORM.object_id == character_id)
        )
    return [_to_schema(r) for r in q.all()]


def create_relation(db: Session, project_id: str, data: RelationCreate) -> Relation:
    o = RelationORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        subject_id=data.subject_id,
        object_id=data.object_id,
        relation_type=data.relation_type,
        strength=data.strength,
        note=data.note,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def get_relation(db: Session, project_id: str, relation_id: str):
    return (
        db.query(RelationORM)
        .filter_by(project_id=project_id, id=relation_id)
        .first()
    )


def update_relation(
    db: Session, project_id: str, relation_id: str, data: RelationUpdate
) -> Relation | None:
    o = get_relation(db, project_id, relation_id)
    if o is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(o, field, value)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def delete_relation(db: Session, project_id: str, relation_id: str) -> bool:
    o = get_relation(db, project_id, relation_id)
    if o is None:
        return False
    db.delete(o)
    db.commit()
    return True
