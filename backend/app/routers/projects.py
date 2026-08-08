"""作品（项目）隔离管理（API接口规范.md §1）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.schemas.project import ProjectCreate, ProjectUpdate
from app.core.response import ok, paginated
from app.core.database import get_session
from app.services import project_crud

router = APIRouter(tags=["作品"])


@router.post("/projects")
def create_project(body: ProjectCreate, db: Session = Depends(get_session)):
    """新建作品并初始化隔离数据表（§1）。"""
    data = body.model_dump()
    item = project_crud.create_project(db, data)
    return ok(item)


@router.get("/projects")
def list_projects(page: int = 1, page_size: int = 20, db: Session = Depends(get_session)):
    """分页查询作品列表（附 chapter_count）。"""
    items, total = project_crud.list_projects(db, page=page, page_size=page_size)
    return ok(paginated(items, total=total, page=page, page_size=page_size))


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_session)):
    """返回作品详情。"""
    item = project_crud.get_project(db, project_id)
    if item is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    return ok(item)


@router.put("/projects/{project_id}")
def update_project(project_id: str, body: ProjectUpdate, db: Session = Depends(get_session)):
    """修改作品元信息。"""
    item = project_crud.update_project(db, project_id, body.model_dump(exclude_unset=True))
    if item is None:
        raise HTTPException(status_code=404, detail="作品不存在")
    return ok(item)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_session)):
    """级联清空该作品下所有业务数据并删除作品。"""
    ok_flag = project_crud.delete_project(db, project_id)
    if not ok_flag:
        raise HTTPException(status_code=404, detail="作品不存在")
    return ok({"deleted": project_id})
