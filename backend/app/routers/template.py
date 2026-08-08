"""模块8：小说套路模板组件（需求 11）。"""
from fastapi import APIRouter
from app.schemas.template import OutlineGenerateRequest
from app.core.response import ok
from app.services import stubs

router = APIRouter(tags=["套路模板"])


@router.get("/templates")
def list_templates():
    # TODO: 返回内置模板库
    return ok(stubs.list_templates())


@router.post("/projects/{project_id}/templates/{template_id}/outline")
def generate_outline(project_id: str, template_id: str, body: OutlineGenerateRequest):
    # TODO: AI 基于模板+历史摘要拆分大纲
    payload = body.model_dump()
    payload["template_id"] = template_id
    return ok(stubs.generate_outline(project_id, payload))


@router.get("/projects/{project_id}/outlines")
def list_outlines(project_id: str):
    return ok([])


@router.post("/projects/{project_id}/outlines")
def create_outline(project_id: str, body: dict):
    return ok({"id": "ol_placeholder", "project_id": project_id, **body})


@router.put("/projects/{project_id}/outlines/{outline_id}")
def update_outline(project_id: str, outline_id: str, body: dict):
    return ok({"id": outline_id, **body})


@router.delete("/projects/{project_id}/outlines/{outline_id}")
def delete_outline(project_id: str, outline_id: str):
    return ok({"deleted": outline_id})
