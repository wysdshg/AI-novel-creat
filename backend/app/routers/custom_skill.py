"""自定义写作 SKILL API（全局共享）。

注意：本路由前缀是 /global-skills（避免与资料库 Skill 路径 /projects/{id}/skills 冲突）。
端点清单见 docs/接口与组件文档.md §4 写作 SKILL。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.schemas.custom_skill import CustomSkillCreate, CustomSkillUpdate
from app.services import custom_skill_crud as svc

router = APIRouter(prefix="/global-skills", tags=["写作 SKILL（全局）"])


@router.get("", summary="列出自定义 SKILL")
def list_skills(
    trigger: Optional[str] = Query(
        None, description="discussion/chapter/memory/parse/all"
    ),
    enabled_only: bool = Query(False),
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    return ok([s.model_dump(mode="json") for s in svc.list_custom_skills(
        db, trigger=trigger, enabled_only=enabled_only, keyword=keyword
    )])


@router.post("", summary="新建自定义 SKILL")
def create_skill(body: CustomSkillCreate, db: Session = Depends(get_session)):
    s = svc.create_custom_skill(db, body)
    return ok(s.model_dump(mode="json"))


@router.get("/{skill_id}", summary="SKILL 详情")
def get_skill(skill_id: str, db: Session = Depends(get_session)):
    s = svc.get_custom_skill(db, skill_id)
    if s is None:
        raise HTTPException(status_code=404, detail="SKILL 不存在")
    return ok(s.model_dump(mode="json"))


@router.put("/{skill_id}", summary="修改 SKILL")
def update_skill(
    skill_id: str, body: CustomSkillUpdate, db: Session = Depends(get_session)
):
    s = svc.update_custom_skill(db, skill_id, body)
    if s is None:
        raise HTTPException(status_code=404, detail="SKILL 不存在")
    return ok(s.model_dump(mode="json"))


@router.delete("/{skill_id}", summary="删除 SKILL")
def delete_skill(skill_id: str, db: Session = Depends(get_session)):
    if not svc.delete_custom_skill(db, skill_id):
        raise HTTPException(status_code=404, detail="SKILL 不存在")
    return ok({"deleted": skill_id})
