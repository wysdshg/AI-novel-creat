"""设定库 API（全局共享，路径前缀在 main.py 拼 /api/v1）。

端点清单见 docs/接口与组件文档.md §3 设定库。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.schemas.setting import SettingCreate, SettingUpdate
from app.services import setting_crud as svc

router = APIRouter(prefix="/settings", tags=["设定库（全局）"])


@router.get("", summary="列出设定")
def list_settings(
    category: Optional[str] = Query(None, description="境界/货币/体系/规则/其它"),
    keyword: Optional[str] = Query(None, description="名称/描述/标签模糊匹配"),
    template_only: bool = Query(False, description="只返回 is_template=True 的"),
    db: Session = Depends(get_session),
):
    return ok([s.model_dump(mode="json") for s in svc.list_settings(
        db, category=category, keyword=keyword, template_only=template_only
    )])


@router.post("", summary="新建设定")
def create_setting(body: SettingCreate, db: Session = Depends(get_session)):
    s = svc.create_setting(db, body)
    return ok(s.model_dump(mode="json"))


@router.get("/{setting_id}", summary="设定详情")
def get_setting(setting_id: str, db: Session = Depends(get_session)):
    s = svc.get_setting(db, setting_id)
    if s is None:
        raise HTTPException(status_code=404, detail="设定不存在")
    return ok(s.model_dump(mode="json"))


@router.put("/{setting_id}", summary="修改设定")
def update_setting(
    setting_id: str, body: SettingUpdate, db: Session = Depends(get_session)
):
    s = svc.update_setting(db, setting_id, body)
    if s is None:
        raise HTTPException(status_code=404, detail="设定不存在")
    return ok(s.model_dump(mode="json"))


@router.delete("/{setting_id}", summary="删除设定")
def delete_setting(setting_id: str, db: Session = Depends(get_session)):
    if not svc.delete_setting(db, setting_id):
        raise HTTPException(status_code=404, detail="设定不存在")
    return ok({"deleted": setting_id})
