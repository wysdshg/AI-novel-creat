"""角色库 CRUD 服务（模块1：分作品资料库）。

分作品隔离通过 project_id 实现：所有查询/写入均按 project_id 过滤。
此处仅实现角色实体；技能/关系/势力等沿用 routers/database.py 的占位桩。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.orm import CharacterORM
from app.schemas.database import Character, CharacterCreate, CharacterUpdate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_schema(o: CharacterORM) -> Character:
    return Character(
        id=o.id,
        name=o.name,
        role_type=o.role_type,
        age=o.age,
        gender=o.gender,
        personality=o.personality,
        background=o.background,
        talent=o.talent,
        current_level=o.current_level,
        skills=o.skills or [],
        relationship_network=o.relationship_network or [],
        brief=o.brief,
        network_x=o.network_x,
        network_y=o.network_y,
        created_at=o.created_at,
        updated_at=o.updated_at,
    )


def list_characters(db: Session, project_id: str) -> list[Character]:
    rows = (
        db.query(CharacterORM)
        .filter_by(project_id=project_id)
        .order_by(CharacterORM.created_at)
        .all()
    )
    return [_to_schema(r) for r in rows]


def create_character(db: Session, project_id: str, data: CharacterCreate) -> Character:
    now = _now()
    o = CharacterORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        name=data.name,
        role_type=data.role_type,
        age=data.age,
        gender=data.gender,
        personality=data.personality,
        background=data.background,
        talent=data.talent,
        current_level=data.current_level,
        skills=data.skills,
        relationship_network=data.relationship_network,
        brief=data.brief,
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def get_character(db: Session, project_id: str, character_id: str):
    return (
        db.query(CharacterORM)
        .filter_by(project_id=project_id, id=character_id)
        .first()
    )


def update_character(
    db: Session, project_id: str, character_id: str, data: CharacterUpdate
) -> Character | None:
    o = get_character(db, project_id, character_id)
    if o is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(o, field, value)
    o.updated_at = _now()
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def delete_character(db: Session, project_id: str, character_id: str) -> bool:
    o = get_character(db, project_id, character_id)
    if o is None:
        return False
    db.delete(o)
    db.commit()
    return True
