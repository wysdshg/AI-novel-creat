"""参考文档模块（每本小说可手动上传，供 AI 生成时参考读取）。

路径前缀 /api/v1/projects/{project_id}/references，由 main.py 统一挂 /api/v1。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.schemas.reference import ReferenceDocCreate, ReferenceDoc, ReferenceDocSummary, ReferenceCatalogItem
from app.services import reference_crud as svc

router = APIRouter(tags=["参考文档"])


@router.post("/projects/{project_id}/references", summary="上传参考文档")
def upload_reference(project_id: str, body: ReferenceDocCreate, db: Session = Depends(get_session)):
    return ok(svc.create_reference(db, project_id, body).model_dump(mode="json"))


@router.get("/projects/{project_id}/references", summary="列出参考文档（不含正文）")
def list_references(project_id: str, db: Session = Depends(get_session)):
    rows = svc.list_references(db, project_id)
    return ok([r.model_dump(mode="json") for r in rows])


@router.get("/projects/{project_id}/references/catalog", summary="参考文件目录（按需加载用，含全局池）")
def reference_catalog(project_id: str, include_global: bool = True, db: Session = Depends(get_session)):
    """给 AI / 前端用的「文件清单」：id/名/摘要/标签/token估算/locked。

    include_global=true（默认）时一并列出全局参考资料池，允许在线拉取。
    """
    items = svc.build_catalog(db, project_id, include_global=include_global)
    return ok([it.model_dump(mode="json") for it in items])


@router.get("/projects/{project_id}/references/{doc_id}", summary="获取单个参考文档（含正文）")
def get_reference(project_id: str, doc_id: str, db: Session = Depends(get_session)):
    doc = svc.get_reference(db, project_id, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="参考文档不存在")
    return ok(doc.model_dump(mode="json"))


@router.delete("/projects/{project_id}/references/{doc_id}", summary="删除参考文档")
def delete_reference(project_id: str, doc_id: str, db: Session = Depends(get_session)):
    if not svc.delete_reference(db, project_id, doc_id):
        raise HTTPException(status_code=404, detail="参考文档不存在")
    return ok({"deleted": doc_id})
