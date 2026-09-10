"""模块6：伏笔线索自动化管理（需求 9）。

2026-09-10（Phase 2.1）从桩转真实：写入侧由 `ingestion` 每章自动回注
（`foreshadow_crud.sync_from_actions`），本模块提供查询与人工增删改。
读取侧的上下文注入见 `core/context/layers.py:layer_foreshadows`（早已实现）。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.schemas.database import ForeshadowCreate, ForeshadowUpdate
from app.services import foreshadow_crud as svc

router = APIRouter(tags=["伏笔管理"])


@router.post("/projects/{project_id}/foreshadows", summary="新建伏笔")
def create_foreshadow(project_id: str, body: ForeshadowCreate,
                      db: Session = Depends(get_session)):
    return ok(svc.create_foreshadow(db, project_id, body))


@router.get("/projects/{project_id}/foreshadows", summary="伏笔列表（可按状态过滤）")
def list_foreshadows(project_id: str, status: str | None = None,
                     db: Session = Depends(get_session)):
    return ok(svc.list_foreshadows(db, project_id, status))


@router.get("/projects/{project_id}/foreshadows/active", summary="可触发伏笔（未回收）")
def get_active_foreshadows(project_id: str, limit: int = Query(20, ge=1, le=100),
                           db: Session = Depends(get_session)):
    return ok(svc.get_active_foreshadows(db, project_id, limit))


@router.post("/projects/{project_id}/foreshadows/detect", summary="AI 自动识别伏笔")
def detect_foreshadows(project_id: str, chapter_id: str):
    """未实现（显式 501）。

    说明：伏笔识别**已在写后摄取里自动完成**——`ingestion` 每章抽取
    `foreshadow_actions` 并回注，无需手动触发。此端点原为桩（恒返回 `[]`，
    属假绿灯），现下架；如需对历史章节补抽，用「重跑摄取」(POST .../memory/ingest)。
    """
    raise HTTPException(
        status_code=501,
        detail="该端点未实现。伏笔识别已在写后摄取中自动完成；"
               "若要对某一章补抽，请使用「重跑摄取」(POST .../memory/ingest)。",
    )


@router.put("/projects/{project_id}/foreshadows/{foreshadow_id}", summary="修改伏笔")
def update_foreshadow(project_id: str, foreshadow_id: str, body: ForeshadowUpdate,
                      db: Session = Depends(get_session)):
    updated = svc.update_foreshadow(db, project_id, foreshadow_id, body)
    if updated is None:
        raise HTTPException(status_code=404, detail="伏笔不存在")
    return ok(updated)


@router.delete("/projects/{project_id}/foreshadows/{foreshadow_id}", summary="删除伏笔")
def delete_foreshadow(project_id: str, foreshadow_id: str,
                      db: Session = Depends(get_session)):
    if not svc.delete_foreshadow(db, project_id, foreshadow_id):
        raise HTTPException(status_code=404, detail="伏笔不存在")
    return ok({"deleted": foreshadow_id})


@router.post("/projects/{project_id}/foreshadows/{foreshadow_id}/activate",
             summary="标记伏笔已回收")
def activate_foreshadow(project_id: str, foreshadow_id: str,
                        activated_chapter: int | None = None,
                        db: Session = Depends(get_session)):
    updated = svc.activate_foreshadow(db, project_id, foreshadow_id, activated_chapter)
    if updated is None:
        raise HTTPException(status_code=404, detail="伏笔不存在")
    return ok(updated)
