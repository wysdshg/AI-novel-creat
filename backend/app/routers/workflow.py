"""工作流 API（全局共享）。

端点清单见 docs/接口与组件文档.md §5 工作流。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate
from app.services import workflow_crud as svc

router = APIRouter(prefix="/workflows", tags=["工作流（全局）"])


@router.get("", summary="列出工作流")
def list_workflows(
    active_only: bool = Query(False, description="只取 is_active=True"),
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    return ok([w.model_dump(mode="json", by_alias=True) for w in svc.list_workflows(
        db, active_only=active_only, keyword=keyword
    )])


@router.post("", summary="新建工作流")
def create_workflow(body: WorkflowCreate, db: Session = Depends(get_session)):
    w = svc.create_workflow(db, body)
    return ok(w.model_dump(mode="json", by_alias=True))


@router.get("/{wf_id}", summary="工作流详情")
def get_workflow(wf_id: str, db: Session = Depends(get_session)):
    w = svc.get_workflow(db, wf_id)
    if w is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return ok(w.model_dump(mode="json", by_alias=True))


@router.put("/{wf_id}", summary="修改工作流")
def update_workflow(
    wf_id: str, body: WorkflowUpdate, db: Session = Depends(get_session)
):
    w = svc.update_workflow(db, wf_id, body)
    if w is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return ok(w.model_dump(mode="json", by_alias=True))


@router.delete("/{wf_id}", summary="删除工作流")
def delete_workflow(wf_id: str, db: Session = Depends(get_session)):
    if not svc.delete_workflow(db, wf_id):
        raise HTTPException(status_code=404, detail="工作流不存在")
    return ok({"deleted": wf_id})


@router.post("/{wf_id}/duplicate", summary="复制工作流（id 重新生成，name 加'(副本)'）")
def duplicate_workflow(wf_id: str, db: Session = Depends(get_session)):
    w = svc.duplicate_workflow(db, wf_id)
    if w is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return ok(w.model_dump(mode="json", by_alias=True))
