"""模块7：剧情走向推荐（需求 5）。"""
from fastapi import APIRouter
from app.core.response import ok
from app.services import stubs

router = APIRouter(tags=["走向推荐"])


@router.post("/projects/{project_id}/chapters/{chapter_id}/directions")
def recommend_directions(project_id: str, chapter_id: str):
    # TODO: 读取结尾剧情/人物状态/未触发伏笔 → 推演 3~5 条（温度 0.7）
    return ok(stubs.recommend_directions(project_id, chapter_id))


@router.get("/projects/{project_id}/chapters/{chapter_id}/directions")
def list_directions(project_id: str, chapter_id: str):
    return ok([])


@router.post("/projects/{project_id}/directions/{direction_id}/select")
def select_direction(project_id: str, direction_id: str):
    # TODO: 选中走向 → 自动加入下一轮商讨缓存
    return ok({"selected": direction_id, "added_to_discussion": True})
