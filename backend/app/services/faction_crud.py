"""势力库 CRUD 服务（模块1：分作品资料库）。

分作品隔离通过 project_id 实现：所有查询/写入均按 project_id 过滤。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.orm import FactionORM
from app.schemas.database import Faction, FactionCreate, FactionUpdate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_schema(o: FactionORM) -> Faction:
    return Faction(
        id=o.id,
        name=o.name,
        description=o.description,
        leader_id=o.leader_id,
        members=o.members or [],
        status=o.status,
    )


def list_factions(db: Session, project_id: str) -> list[Faction]:
    rows = (
        db.query(FactionORM)
        .filter_by(project_id=project_id)
        .order_by(FactionORM.created_at)
        .all()
    )
    return [_to_schema(r) for r in rows]


def create_faction(db: Session, project_id: str, data: FactionCreate) -> Faction:
    now = _now()
    o = FactionORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        name=data.name,
        description=data.description,
        leader_id=data.leader_id,
        members=data.members or [],
        status=data.status,
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def get_faction(db: Session, project_id: str, faction_id: str):
    return (
        db.query(FactionORM)
        .filter_by(project_id=project_id, id=faction_id)
        .first()
    )


def update_faction(
    db: Session, project_id: str, faction_id: str, data: FactionUpdate
) -> Faction | None:
    o = get_faction(db, project_id, faction_id)
    if o is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(o, field, value)
    o.updated_at = _now()
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def delete_faction(db: Session, project_id: str, faction_id: str) -> bool:
    o = get_faction(db, project_id, faction_id)
    if o is None:
        return False
    db.delete(o)
    db.commit()
    return True
