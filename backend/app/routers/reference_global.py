"""全局共享参考资料（「参考资料」池）。

与「每本小说参考文档」共用 reference_docs 表，以 GLOBAL_PROJECT_ID 作特殊 project_id 隔离；
在新建小说时可挑选若干全局参考资料，复制进该小说（见 import-global 端点）。
"""
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.schemas.reference import ReferenceDocCreate, ReferenceDoc, ReferenceDocSummary, ReferenceCatalogItem
from app.services import reference_crud as svc

router = APIRouter(tags=["参考资料(全局)"])

GLOBAL = svc.GLOBAL_PROJECT_ID


class ImportBody(BaseModel):
    doc_ids: List[str] = []


@router.get("/references/global", summary="列出全局参考资料")
def list_global(db: Session = Depends(get_session)):
    rows = svc.list_references(db, GLOBAL)
    return ok([r.model_dump(mode="json") for r in rows])


@router.get("/references/global/catalog", summary="全局参考文件目录（按需加载用）")
def global_catalog(db: Session = Depends(get_session)):
    """给 AI / 前端用的全局资料「文件清单」：id/名/摘要/标签/token估算/locked。"""
    items = svc.build_catalog(db, GLOBAL, include_global=False)
    return ok([it.model_dump(mode="json") for it in items])


@router.post("/references/global", summary="上传全局参考资料")
def create_global(body: ReferenceDocCreate, db: Session = Depends(get_session)):
    return ok(svc.create_reference(db, GLOBAL, body).model_dump(mode="json"))


@router.get("/references/global/{doc_id}", summary="获取单个全局参考资料（含正文）")
def get_global(doc_id: str, db: Session = Depends(get_session)):
    doc = svc.get_reference(db, GLOBAL, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="全局参考资料不存在")
    return ok(doc.model_dump(mode="json"))


@router.delete("/references/global/{doc_id}", summary="删除全局参考资料")
def delete_global(doc_id: str, db: Session = Depends(get_session)):
    if not svc.delete_reference(db, GLOBAL, doc_id):
        raise HTTPException(status_code=404, detail="全局参考资料不存在")
    return ok({"deleted": doc_id})


@router.post("/projects/{project_id}/references/import-global", summary="将选中的全局参考资料复制进小说")
def import_global(project_id: str, body: ImportBody, db: Session = Depends(get_session)):
    n = svc.import_global_references(db, project_id, body.doc_ids or [])
    return ok({"imported": n})
