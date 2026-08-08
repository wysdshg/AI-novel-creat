"""模块1：分作品资料库系统（需求 1、4、10）。路径前缀见 main.py 的 /api/v1。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.schemas.database import (
    CharacterCreate, CharacterUpdate, SkillCreate, SkillUpdate,
    RelationCreate, RelationUpdate, FactionCreate, FactionUpdate,
    LocationCreate, LocationUpdate,
    ForeshadowCreate, ForeshadowUpdate, ValidateRequest, CommandRequest,
)
from app.core.response import ok
from app.core.database import get_session
from app.services import character_crud, faction_crud, location_crud, relation_crud, stubs, config_command

router = APIRouter(tags=["资料库"])


# ---------- 角色（已落地真实持久化） ----------
@router.post("/projects/{project_id}/characters")
def create_character(
    project_id: str,
    body: CharacterCreate,
    db: Session = Depends(get_session),
):
    return ok(character_crud.create_character(db, project_id, body).model_dump(mode="json"))


@router.get("/projects/{project_id}/characters")
def list_characters(
    project_id: str,
    db: Session = Depends(get_session),
):
    return ok([c.model_dump(mode="json") for c in character_crud.list_characters(db, project_id)])


@router.get("/projects/{project_id}/characters/{character_id}")
def get_character(project_id: str, character_id: str, db: Session = Depends(get_session)):
    o = character_crud.get_character(db, project_id, character_id)
    if o is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return ok(character_crud._to_schema(o).model_dump(mode="json"))


@router.put("/projects/{project_id}/characters/{character_id}")
def update_character(
    project_id: str,
    character_id: str,
    body: CharacterUpdate,
    db: Session = Depends(get_session),
):
    updated = character_crud.update_character(db, project_id, character_id, body)
    if updated is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return ok(updated.model_dump(mode="json"))


@router.delete("/projects/{project_id}/characters/{character_id}")
def delete_character(project_id: str, character_id: str, db: Session = Depends(get_session)):
    if not character_crud.delete_character(db, project_id, character_id):
        raise HTTPException(status_code=404, detail="角色不存在")
    return ok({"deleted": character_id})


# ---------- 技能 ----------
@router.post("/projects/{project_id}/skills")
def create_skill(project_id: str, body: SkillCreate):
    return ok({"id": "sk_placeholder", **body.model_dump()})


@router.get("/projects/{project_id}/skills")
def list_skills(project_id: str):
    return ok([])


@router.get("/projects/{project_id}/skills/{skill_id}")
def get_skill(project_id: str, skill_id: str):
    return ok({"id": skill_id})


@router.put("/projects/{project_id}/skills/{skill_id}")
def update_skill(project_id: str, skill_id: str, body: SkillUpdate):
    return ok({"id": skill_id, **body.model_dump(exclude_unset=True)})


@router.delete("/projects/{project_id}/skills/{skill_id}")
def delete_skill(project_id: str, skill_id: str):
    return ok({"deleted": skill_id})


# ---------- 关系（已落地真实持久化） ----------
@router.post("/projects/{project_id}/relations")
def create_relation(
    project_id: str,
    body: RelationCreate,
    db: Session = Depends(get_session),
):
    return ok(relation_crud.create_relation(db, project_id, body).model_dump(mode="json"))


@router.get("/projects/{project_id}/relations")
def list_relations(
    project_id: str,
    character_id: str | None = None,
    db: Session = Depends(get_session),
):
    return ok([r.model_dump(mode="json") for r in relation_crud.list_relations(db, project_id, character_id)])


@router.put("/projects/{project_id}/relations/{relation_id}")
def update_relation(
    project_id: str,
    relation_id: str,
    body: RelationUpdate,
    db: Session = Depends(get_session),
):
    updated = relation_crud.update_relation(db, project_id, relation_id, body)
    if updated is None:
        raise HTTPException(status_code=404, detail="关系不存在")
    return ok(updated.model_dump(mode="json"))


@router.delete("/projects/{project_id}/relations/{relation_id}")
def delete_relation(
    project_id: str,
    relation_id: str,
    db: Session = Depends(get_session),
):
    if not relation_crud.delete_relation(db, project_id, relation_id):
        raise HTTPException(status_code=404, detail="关系不存在")
    return ok({"deleted": relation_id})


# ---------- 势力（已落地真实持久化） ----------
@router.post("/projects/{project_id}/factions")
def create_faction(
    project_id: str,
    body: FactionCreate,
    db: Session = Depends(get_session),
):
    return ok(faction_crud.create_faction(db, project_id, body).model_dump(mode="json"))


@router.get("/projects/{project_id}/factions")
def list_factions(
    project_id: str,
    db: Session = Depends(get_session),
):
    return ok([f.model_dump(mode="json") for f in faction_crud.list_factions(db, project_id)])


@router.get("/projects/{project_id}/factions/{faction_id}")
def get_faction(project_id: str, faction_id: str, db: Session = Depends(get_session)):
    o = faction_crud.get_faction(db, project_id, faction_id)
    if o is None:
        raise HTTPException(status_code=404, detail="势力不存在")
    return ok(faction_crud._to_schema(o).model_dump(mode="json"))


@router.put("/projects/{project_id}/factions/{faction_id}")
def update_faction(
    project_id: str,
    faction_id: str,
    body: FactionUpdate,
    db: Session = Depends(get_session),
):
    updated = faction_crud.update_faction(db, project_id, faction_id, body)
    if updated is None:
        raise HTTPException(status_code=404, detail="势力不存在")
    return ok(updated.model_dump(mode="json"))


@router.delete("/projects/{project_id}/factions/{faction_id}")
def delete_faction(project_id: str, faction_id: str, db: Session = Depends(get_session)):
    if not faction_crud.delete_faction(db, project_id, faction_id):
        raise HTTPException(status_code=404, detail="势力不存在")
    return ok({"deleted": faction_id})


# ---------- 地点（已落地真实持久化） ----------
@router.post("/projects/{project_id}/locations")
def create_location(
    project_id: str,
    body: LocationCreate,
    db: Session = Depends(get_session),
):
    return ok(location_crud.create_location(db, project_id, body).model_dump(mode="json"))


@router.get("/projects/{project_id}/locations")
def list_locations(
    project_id: str,
    db: Session = Depends(get_session),
):
    return ok([l.model_dump(mode="json") for l in location_crud.list_locations(db, project_id)])


@router.get("/projects/{project_id}/locations/{location_id}")
def get_location(project_id: str, location_id: str, db: Session = Depends(get_session)):
    o = location_crud.get_location(db, project_id, location_id)
    if o is None:
        raise HTTPException(status_code=404, detail="地点不存在")
    return ok(location_crud._to_schema(o).model_dump(mode="json"))


@router.put("/projects/{project_id}/locations/{location_id}")
def update_location(
    project_id: str,
    location_id: str,
    body: LocationUpdate,
    db: Session = Depends(get_session),
):
    updated = location_crud.update_location(db, project_id, location_id, body)
    if updated is None:
        raise HTTPException(status_code=404, detail="地点不存在")
    return ok(updated.model_dump(mode="json"))


@router.delete("/projects/{project_id}/locations/{location_id}")
def delete_location(project_id: str, location_id: str, db: Session = Depends(get_session)):
    if not location_crud.delete_location(db, project_id, location_id):
        raise HTTPException(status_code=404, detail="地点不存在")
    return ok({"deleted": location_id})


@router.get("/projects/{project_id}/locations/{location_id}/geo-relations")
def location_geo_relations(project_id: str, location_id: str, db: Session = Depends(get_session)):
    """同位面内其他地点的方位与距离（坐标自动推导，无需手填）。"""
    res = location_crud.geo_relations(db, project_id, location_id)
    if res is None:
        raise HTTPException(status_code=404, detail="地点不存在")
    return ok(res)


# ---------- 设定校验（需求 4） ----------
@router.post("/projects/{project_id}/validate")
def validate_settings(project_id: str, body: ValidateRequest):
    return ok(stubs.validate_settings(project_id, body.model_dump()))


# ---------- 配置对话：自然语言自动整理资料库（需求 10） ----------
@router.post("/projects/{project_id}/command")
def run_command(project_id: str, body: CommandRequest, db: Session = Depends(get_session)):
    return config_command.run(db, project_id, body.text, body.dry_run)
