"""作品（项目）隔离管理（API接口规范.md §1）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List

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


# ---------------------------------------------------------------------------
# 小说设定库管理
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/settings")
def get_project_settings(project_id: str, db: Session = Depends(get_session)):
    """返回本小说选中的设定库 ID 列表及完整设定详情。"""
    from app.models.orm import ProjectORM
    orm = db.query(ProjectORM).filter_by(id=project_id).first()
    if not orm:
        raise HTTPException(status_code=404, detail="作品不存在")
    return ok({"setting_ids": orm.setting_ids or []})


@router.put("/projects/{project_id}/settings")
def update_project_settings(
    project_id: str,
    body: dict,
    db: Session = Depends(get_session),
):
    """更新本小说选中的设定库（全量替换）。"""
    from app.models.orm import ProjectORM
    orm = db.query(ProjectORM).filter_by(id=project_id).first()
    if not orm:
        raise HTTPException(status_code=404, detail="作品不存在")
    ids = body.get("setting_ids")
    if ids is not None:
        # 校验所有 id 都存在于全局设定库中
        from app.models.orm import SettingORM
        valid_ids = set(r[0] for r in db.query(SettingORM.id).all())
        invalid = [i for i in ids if i not in valid_ids]
        if invalid:
            raise HTTPException(status_code=400, detail=f"无效的设定 ID: {invalid[:5]}")
        orm.setting_ids = ids
    else:
        orm.setting_ids = None  # null = 全量注入（向后兼容）
    db.commit()
    return ok({"setting_ids": orm.setting_ids or []})
