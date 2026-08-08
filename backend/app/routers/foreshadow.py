"""模块6：伏笔线索自动化管理（需求 9）。"""
from fastapi import APIRouter
from app.schemas.database import ForeshadowCreate, ForeshadowUpdate
from app.core.response import ok
from app.services import stubs

router = APIRouter(tags=["伏笔管理"])


@router.post("/projects/{project_id}/foreshadows")
def create_foreshadow(project_id: str, body: ForeshadowCreate):
    return ok({"id": "fs_placeholder", **body.model_dump()})


@router.get("/projects/{project_id}/foreshadows")
def list_foreshadows(project_id: str, status: str | None = None):
    return ok(stubs.list_foreshadows(project_id, status))


@router.put("/projects/{project_id}/foreshadows/{foreshadow_id}")
def update_foreshadow(project_id: str, foreshadow_id: str, body: ForeshadowUpdate):
    return ok({"id": foreshadow_id, **body.model_dump(exclude_unset=True)})


@router.delete("/projects/{project_id}/foreshadows/{foreshadow_id}")
def delete_foreshadow(project_id: str, foreshadow_id: str):
    return ok({"deleted": foreshadow_id})


@router.post("/projects/{project_id}/foreshadows/detect")
def detect_foreshadows(project_id: str, chapter_id: str):
    # TODO: AI 根据章节正文自动识别新增伏笔
    return ok(stubs.detect_foreshadows(project_id, chapter_id))


@router.get("/projects/{project_id}/foreshadows/active")
def get_active_foreshadows(project_id: str):
    # TODO: 生成前置检索，匹配当前剧情场景筛出可触发伏笔
    return ok(stubs.get_active_foreshadows(project_id))


@router.post("/projects/{project_id}/foreshadows/{foreshadow_id}/activate")
def activate_foreshadow(project_id: str, foreshadow_id: str, activated_chapter: int):
    # TODO: 标记伏笔启用回收，状态→done
    return ok({"id": foreshadow_id, "activated_chapter": activated_chapter, "status": "done"})
