"""卷（volume）路由：4 级结构的小说 → 卷 → 篇 → 章 ——「卷」层 API。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.schemas.volume import VolumeCreate, VolumeUpdate
from app.services import volume_crud

router = APIRouter(tags=["卷（volume）"])


def _to_dict(o):
    return {
        "id": o.id,
        "project_id": o.project_id,
        "name": o.name,
        "summary": o.summary,
        "sort_order": o.sort_order,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
    }


@router.get("/projects/{project_id}/volumes")
def list_volumes(project_id: str, db: Session = Depends(get_session)):
    return ok([_to_dict(v) for v in volume_crud.list_volumes(db, project_id)])


@router.post("/projects/{project_id}/volumes")
def create_volume(project_id: str, body: VolumeCreate, db: Session = Depends(get_session)):
    o = volume_crud.create_volume(db, project_id, body)
    return ok(_to_dict(o))


@router.get("/projects/{project_id}/volumes/{volume_id}")
def get_volume(project_id: str, volume_id: str, db: Session = Depends(get_session)):
    o = volume_crud.get_volume(db, project_id, volume_id)
    if not o:
        return ok(None)
    return ok(_to_dict(o))


@router.put("/projects/{project_id}/volumes/{volume_id}")
def update_volume(project_id: str, volume_id: str, body: VolumeUpdate, db: Session = Depends(get_session)):
    o = volume_crud.update_volume(db, project_id, volume_id, body)
    if not o:
        return ok({"updated": False, "id": volume_id})
    return ok(_to_dict(o))


@router.delete("/projects/{project_id}/volumes/{volume_id}")
def delete_volume(project_id: str, volume_id: str, db: Session = Depends(get_session)):
    ok_flag = volume_crud.delete_volume(db, project_id, volume_id)
    return ok({"deleted": volume_id, "ok": ok_flag})
