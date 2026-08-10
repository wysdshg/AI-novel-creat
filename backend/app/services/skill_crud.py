"""技能（Skill）CRUD —— 资料库 §2.2（按 project_id 隔离的角色技能）。

注意：本模块与全局写作 SKILL（custom_skill.py / routers/custom_skill.py）独立。
- Skill（这里）：与角色绑定的「技能」，按 project_id 隔离 —— 接口 /projects/{project_id}/skills
- CustomSkill（全局）：AI 提示词模板，无 project —— 接口 /global-skills
"""
import uuid
from sqlalchemy.orm import Session

from app.models.orm import SkillORM
from app.schemas.database import Skill, SkillCreate, SkillUpdate


def _to_schema(o: SkillORM) -> Skill:
    return Skill(
        id=o.id,
        name=o.name,
        level=o.level,
        effect=o.effect,
        limitation=o.limitation,
        owner_id=o.owner_id,
        side_effect=o.side_effect,
        unlock_condition=o.unlock_condition,
    )


def list_skills(db: Session, project_id: str) -> list[Skill]:
    rows = db.query(SkillORM).filter_by(project_id=project_id).order_by(SkillORM.name).all()
    return [_to_schema(r) for r in rows]


def get_skill(db: Session, project_id: str, skill_id: str) -> Skill | None:
    o = db.query(SkillORM).filter_by(project_id=project_id, id=skill_id).first()
    return _to_schema(o) if o else None


def create_skill(db: Session, project_id: str, data: SkillCreate) -> Skill:
    o = SkillORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        name=data.name,
        level=data.level,
        effect=data.effect,
        limitation=data.limitation,
        owner_id=data.owner_id,
        side_effect=data.side_effect,
        unlock_condition=data.unlock_condition,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def update_skill(
    db: Session, project_id: str, skill_id: str, data: SkillUpdate
) -> Skill | None:
    o = db.query(SkillORM).filter_by(project_id=project_id, id=skill_id).first()
    if o is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(o, field, value)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def delete_skill(db: Session, project_id: str, skill_id: str) -> bool:
    o = db.query(SkillORM).filter_by(project_id=project_id, id=skill_id).first()
    if o is None:
        return False
    db.delete(o)
    db.commit()
    return True
