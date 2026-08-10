"""AI 辅助能力总入口：写库确认、AI 味检测、SKILL 调度查询、全局配置、资料推荐。

这些端点串起需求 1/2/5/6 的「人机交接口」——
AI 提出建议，作者点确认，系统才真正落库。
默认走这条路而不是让模型直接写表：本地小模型抽错一个境界，
后面每一章都会跟着错，代价远大于多点一次鼠标。
"""
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.schemas.database import CharacterCreate, FactionCreate, LocationCreate
from app.services import (
    app_config, character_crud, faction_crud, humanizer, location_crud,
    memory_crud, reference_crud, seed_skills, skill_dispatch,
)

router = APIRouter(tags=["AI 辅助"])


# ===========================================================================
# 需求 5：AI 味检测
# ===========================================================================

class ScanRequest(BaseModel):
    text: str
    scene: str = "novel"


@router.post("/humanize/scan")
def humanize_scan(body: ScanRequest):
    """纯正则扫描，不调模型：零 token、零等待、也不会把作者的原文改崩。"""
    if not (body.text or "").strip():
        return ok({"score": 100.0, "grade": "空文本", "issues": [], "issue_count": 0})
    return ok(humanizer.scan(body.text, scene=body.scene))


@router.get("/humanize/prompt")
def humanize_prompt(scene: str = "novel", level: str = "normal"):
    """返回将被注入生成提示词的去 AI 味约束——让作者看得见 AI 被要求了什么。"""
    return ok({"scene": scene, "level": level,
               "block": humanizer.build_prompt_block(scene=scene, level=level)})


@router.post("/projects/{project_id}/chapters/{chapter_id}/scan")
def scan_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_session)):
    from app.models.orm import ChapterORM
    c = db.query(ChapterORM).filter_by(id=chapter_id, project_id=project_id).first()
    if c is None:
        raise HTTPException(status_code=404, detail="章节不存在")
    return ok(humanizer.scan(c.content or "", scene="novel"))


# ===========================================================================
# 需求 6：SKILL 调度
# ===========================================================================

@router.get("/skills/dispatch")
def skill_dispatch_explain(trigger: str = "chapter", db: Session = Depends(get_session)):
    """当前 trigger 下哪些 SKILL 会生效、哪些被同类更高优先级的挤掉。

    「为什么我写的技能没起作用」是这类系统最常见的困惑，
    与其让作者猜，不如把调度结果直接摊开。
    """
    if trigger not in skill_dispatch.VALID_TRIGGERS:
        raise HTTPException(status_code=400,
                            detail=f"trigger 必须是 {skill_dispatch.VALID_TRIGGERS} 之一")
    return ok(skill_dispatch.explain(db, trigger))


@router.post("/skills/seed")
def install_seed_skills(overwrite: bool = False, db: Session = Depends(get_session)):
    """安装 6 条预置写作 SKILL（幂等，重复调用不会产生副本）。"""
    return ok(seed_skills.install(db, overwrite=overwrite))


# ===========================================================================
# 全局配置（KV）
# ===========================================================================

@router.get("/config")
def get_config(db: Session = Depends(get_session)):
    return ok({"values": app_config.get_all(db), "schema": app_config.describe()})


@router.put("/config")
def update_config(payload: dict = Body(...), db: Session = Depends(get_session)):
    return ok(app_config.set_many(db, payload))


# ===========================================================================
# 需求 2-A：从全局资料池推荐值得借鉴的资料
# ===========================================================================

@router.get("/projects/{project_id}/references/recommend")
def recommend_references(project_id: str, top_k: int = 8, db: Session = Depends(get_session)):
    return ok(reference_crud.recommend_global_references(db, project_id, top_k=top_k))


# ===========================================================================
# 需求 1：AI 抽出的新实体，作者确认后写库
# ===========================================================================

class EntityItem(BaseModel):
    kind: str            # character | faction | location
    name: str
    brief: str = ""
    # ---- 角色专属字段（kind=character 时使用）----
    personality: str = ""
    background: str = ""
    talent: str = ""
    current_level: str = ""
    role_type: str = ""
    age: int | None = None
    gender: str = ""
    skills: list[str] = []
    relationship_network: list[str] = []
    # ---- 势力/地点通用 ----
    description: str = ""


class ConfirmEntitiesRequest(BaseModel):
    chapter_id: str | None = None
    items: list[EntityItem] = []


@router.post("/projects/{project_id}/memory/confirm-entities")
def confirm_entities(project_id: str, body: ConfirmEntitiesRequest,
                     db: Session = Depends(get_session)):
    """把 AI 抽到的新角色/势力/地点正式写进资料库。

    重名的直接跳过——同名实体在小说里通常就是同一个，
    重复建卡会让后续注入出现两份互相矛盾的设定。
    """
    created, skipped = [], []
    for it in body.items:
        name = (it.name or "").strip()
        if not name:
            continue
        try:
            if it.kind == "character":
                exists = any(
                    c.name == name for c in character_crud.list_characters(db, project_id)
                )
                if exists:
                    skipped.append({"name": name, "reason": "同名角色已存在"})
                    continue
                # 构建角色创建参数：把 AI 抽到的属性全部映射进去
                char_fields = {"name": name, "role_type": it.role_type or "配角"}
                for _f in ("personality", "background", "talent", "current_level",
                           "age", "gender", "brief"):
                    val = getattr(it, _f, None)
                    if val is not None and (not isinstance(val, str) or val.strip()):
                        char_fields[_f] = val
                # 列表型字段
                if it.skills:
                    char_fields["skills"] = it.skills
                if it.relationship_network:
                    char_fields["relationship_network"] = it.relationship_network
                # brief 兜底：如果没有 brief 但有 personality，拼一个
                if not char_fields.get("brief") and char_fields.get("personality"):
                    parts = [char_fields["personality"]]
                    if char_fields.get("talent"):
                        parts.append(f"天赋：{char_fields['talent']}")
                    if char_fields.get("background"):
                        parts.append(char_fields["background"])
                    char_fields["brief"] = "；".join(parts)
                o = character_crud.create_character(
                    db, project_id,
                    CharacterCreate(**char_fields),
                )
                created.append({"kind": "character", "id": o.id, "name": name})

            elif it.kind == "faction":
                exists = any(f.name == name for f in faction_crud.list_factions(db, project_id))
                if exists:
                    skipped.append({"name": name, "reason": "同名势力已存在"})
                    continue
                desc = it.description or it.brief or ""
                o = faction_crud.create_faction(
                    db, project_id, FactionCreate(name=name, description=desc),
                )
                created.append({"kind": "faction", "id": o.id, "name": name})

            elif it.kind == "location":
                exists = any(l.name == name for l in location_crud.list_locations(db, project_id))
                if exists:
                    skipped.append({"name": name, "reason": "同名地点已存在"})
                    continue
                desc = it.description or it.brief or ""
                o = location_crud.create_location(
                    db, project_id, LocationCreate(name=name, description=desc),
                )
                created.append({"kind": "location", "id": o.id, "name": name})
            else:
                skipped.append({"name": name, "reason": f"未知类型 {it.kind}"})
        except Exception as e:  # noqa: BLE001
            skipped.append({"name": name, "reason": f"写入失败：{str(e)[:100]}"})

    if body.chapter_id:
        memory_crud.set_status(db, project_id, body.chapter_id, "confirmed")

    return ok({"created": created, "skipped": skipped})
