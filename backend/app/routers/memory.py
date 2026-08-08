"""模块5：篇章记忆压缩（需求 8）。"""
from fastapi import APIRouter
from app.core.response import ok
from app.services import stubs

router = APIRouter(tags=["记忆压缩"])


@router.post("/projects/{project_id}/memory/compress")
def compress_memory(project_id: str, chapter_id: str):
    # TODO: 调用 memory 角色模型对章节做结构化压缩
    return ok(stubs.compress_memory(project_id, chapter_id))


@router.get("/projects/{project_id}/memory/summary")
def get_memory_summary(project_id: str):
    # TODO: 最近3章详细 + 更早极简大事记
    return ok(stubs.get_memory_summary(project_id))


@router.get("/projects/{project_id}/memory/events")
def list_major_events(project_id: str):
    return ok([])
