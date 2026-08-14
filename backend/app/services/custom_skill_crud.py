"""自定义写作 SKILL CRUD（全局共享，不按 project 过滤）。

设计参考「印象笔记类提醒规则」：name + trigger + prompt_body。
可扩展点：
- list_by_trigger(trigger)：按触发场景筛（前端 setting 页面可能用）
- bulk_toggle(ids, enabled)：批量开关（前端勾选用）
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.orm import CustomSkillORM
from app.schemas.custom_skill import CustomSkill, CustomSkillCreate, CustomSkillUpdate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_schema(o: CustomSkillORM) -> CustomSkill:
    return CustomSkill.model_validate(o)


def list_custom_skills(
    db: Session,
    trigger: Optional[str] = None,
    enabled_only: bool = False,
    keyword: Optional[str] = None,
) -> list[CustomSkill]:
    q = db.query(CustomSkillORM)
    if trigger:
        q = q.filter(
            (CustomSkillORM.trigger == trigger) | (CustomSkillORM.trigger == "all")
        )
    if enabled_only:
        q = q.filter(CustomSkillORM.enabled.is_(True))
    rows = q.order_by(CustomSkillORM.name).all()
    if keyword:
        k = keyword.lower()
        rows = [
            o for o in rows
            if k in (o.name or "").lower()
            or k in (o.description or "").lower()
            or any(k in str(t).lower() for t in (o.tags or []))
        ]
    return [_to_schema(r) for r in rows]


def create_custom_skill(db: Session, data: CustomSkillCreate) -> CustomSkill:
    now = _now()
    o = CustomSkillORM(
        id=uuid.uuid4().hex,
        name=data.name,
        description=data.description,
        prompt_body=data.prompt_body,
        trigger=data.trigger or "all",
        enabled=data.enabled,
        tags=data.tags or [],
        category=data.category or "通用",
        priority=data.priority if data.priority is not None else 100,
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def get_custom_skill(db: Session, skill_id: str) -> Optional[CustomSkill]:
    o = db.query(CustomSkillORM).filter_by(id=skill_id).first()
    return _to_schema(o) if o else None


def update_custom_skill(
    db: Session, skill_id: str, data: CustomSkillUpdate
) -> Optional[CustomSkill]:
    o = db.query(CustomSkillORM).filter_by(id=skill_id).first()
    if o is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(o, field, value)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def delete_custom_skill(db: Session, skill_id: str) -> bool:
    o = db.query(CustomSkillORM).filter_by(id=skill_id).first()
    if o is None:
        return False
    db.delete(o)
    db.commit()
    return True
