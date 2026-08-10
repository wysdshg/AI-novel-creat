"""设定库 CRUD（全局共享，不按 project 过滤）。

可扩展点：
- 支持 category/keyword 检索（list_filter）
- 模板列表（is_template=True）独立筛选，给"创建小说"流程挑选用
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.orm import SettingORM
from app.schemas.setting import Setting, SettingCreate, SettingUpdate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_schema(o: SettingORM) -> Setting:
    return Setting.model_validate(o)


def list_settings(
    db: Session,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    template_only: bool = False,
) -> list[Setting]:
    q = db.query(SettingORM)
    if category:
        q = q.filter(SettingORM.category == category)
    if template_only:
        q = q.filter(SettingORM.is_template.is_(True))
    if keyword:
        like = f"%{keyword}%"
        # name / description / tags(JSON) 都做模糊匹配（SQLite 用 LIKE）
        from sqlalchemy import or_, func
        q = q.filter(
            or_(
                SettingORM.name.like(like),
                SettingORM.description.like(like),
                func.json_tree_to_string(SettingORM.tags) if False else SettingORM.tags.isnot(None),
            )
        )
    rows = q.order_by(SettingORM.category, SettingORM.name).all()
    # 二次过滤 tags（SQLite JSON LIKE 兼容性差，这里 Python 层处理）
    if keyword:
        k = keyword.lower()
        rows = [
            o for o in rows
            if k in (o.name or "").lower()
            or k in (o.description or "").lower()
            or any(k in str(t).lower() for t in (o.tags or []))
        ]
    return [_to_schema(r) for r in rows]


def create_setting(db: Session, data: SettingCreate) -> Setting:
    now = _now()
    o = SettingORM(
        id=uuid.uuid4().hex,
        name=data.name,
        category=data.category or "其它",
        levels=data.levels or [],
        description=data.description,
        tags=data.tags or [],
        is_template=data.is_template,
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def get_setting(db: Session, setting_id: str) -> Optional[Setting]:
    o = db.query(SettingORM).filter_by(id=setting_id).first()
    return _to_schema(o) if o else None


def update_setting(
    db: Session, setting_id: str, data: SettingUpdate
) -> Optional[Setting]:
    o = db.query(SettingORM).filter_by(id=setting_id).first()
    if o is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(o, field, value)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def delete_setting(db: Session, setting_id: str) -> bool:
    o = db.query(SettingORM).filter_by(id=setting_id).first()
    if o is None:
        return False
    db.delete(o)
    db.commit()
    return True
