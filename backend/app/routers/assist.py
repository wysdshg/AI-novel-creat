"""AI 辅助能力总入口：写库确认、AI 味检测、SKILL 调度查询、全局配置、资料推荐。

这些端点串起需求 1/2/5/6 的「人机交接口」——
AI 提出建议，作者点确认，系统才真正落库。
默认走这条路而不是让模型直接写表：本地小模型抽错一个境界，
后面每一章都会跟着错，代价远大于多点一次鼠标。
"""
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_session
from app.core.response import fail, ok
from app.core.gateway.registry import get_adapter
from app.models.orm import ModelConfigORM, ProjectORM
from app.schemas.database import CharacterCreate, FactionCreate, LocationCreate
from app.services import (
    app_config, character_crud, faction_crud, humanizer, location_crud,
    memory_crud, model_crud, reference_crud, seed_skills, skill_dispatch,
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


# ===========================================================================
# 问题7：章节要素「AI 生成 / 润色」（一键草稿）
# ===========================================================================

class PolishElementRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())  # 允许字段名 model_id（否则 pydantic 警告）
    field_label: str                              # 当前字段名（如「时空背景」）
    current_text: str = ""                        # 已填内容；空 → 生成模式
    mode: str = "auto"                            # auto | generate | polish
    context: dict = {}                            # 本章其他已填要素，保证上下文一致
    model_id: Optional[str] = None                # 前端当前选中的模型；不传回退默认模型


# 字段 key → 中文名（用于把 context 里其余字段拼成可读上下文）
_FIELD_NAMES = {
    "scene_goal": "场景目标",
    "characters": "出场角色",
    "background": "时空背景",
    "conflict": "核心冲突",
    "beats": "情节节拍",
    "hook": "结尾钩子",
    "style": "风格约束",
}


def _strip_wrapper(text: str) -> str:
    """去掉模型偶尔夹带的代码围栏，其余原样返回（系统提示已要求不加引导语）。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t.split("\n", 1)[-1] if "\n" in t else t
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


@router.post("/projects/{project_id}/llm/polish-element")
def polish_element(project_id: str, body: PolishElementRequest,
                   db: Session = Depends(get_session)):
    """为章节结构化要素生成草稿或润色扩写（轻量非流式）。

    - 空文本 → 生成模式：按小说上下文 + 其他已填要素起草；
    - 已填文本 → 润色模式：保留原意、扩写得更具体、与上下文一致。
    - 模型：优先用前端传入的 model_id（与对话页所选一致），查不到/未传则回退默认模型。
    """
    default = model_crud.get_default(db)
    if body.model_id:
        m = model_crud.get_model(db, body.model_id)
        if m and (m.status or "active") == "active":
            default = m
    if default is None or (default.status or "active") != "active":
        return fail(40001, "未配置可用默认模型，请先在「模型配置」添加并设为默认")

    # 小说上下文：类型 + 简介，约束风格与世界观一致性
    proj = db.query(ProjectORM).filter_by(id=project_id).first()
    genre = (proj.genre or "未指定") if proj else "未指定"
    summary = (proj.summary or "").strip() if proj else ""
    if len(summary) > 600:
        summary = summary[:600] + "…"

    # 组装「其他已填要素」上下文（排除当前字段本身，避免自我引用）
    ctx_parts = []
    for key, label in _FIELD_NAMES.items():
        if key in body.context:
            val = (body.context.get(key) or "").strip()
            if val:
                ctx_parts.append(f"- {label}：{val}")
    ctx_block = "\n".join(ctx_parts) if ctx_parts else "（暂无其他已填要素）"

    mode = body.mode
    if mode == "auto":
        mode = "polish" if (body.current_text or "").strip() else "generate"

    if mode == "generate":
        task = (
            f"请为「{body.field_label}」这一章节要素撰写一段具体、可直接用于约束 AI 生成本章的草稿，"
            f"约 120~260 字。要落地到具体的人、事、物、场景，不要空泛口号。"
        )
    else:
        task = (
            f"作者已写「{body.field_label}」如下：\n\"\"\"\n{body.current_text.strip()}\n\"\"\"\n"
            f"请在保留原意与已有信息的前提下，扩写 / 润色得更具体、更有画面感、更有张力，约 120~260 字。"
            f"不要删掉作者已有的关键设定，不要自相矛盾。"
        )

    system_prompt = (
        "你是一位专业网文写作助手，帮助作者起草或润色「章节结构化要素」"
        "（用于约束 AI 生成单章的提纲字段）。\n"
        "规则：\n"
        "1. 只输出该字段的成品内容（中文），不要解释、不要 markdown 标题、不要以「好的 / 以下是」开头。\n"
        "2. 必须与上方的「小说类型 / 简介」和「本章其他要素」保持一致，不得出现矛盾设定。\n"
        "3. 具体、有画面、有信息量；避免空泛抒情与口号式语句。\n"
        "4. 去除 AI 痕迹：禁止「不是A不是B只是C」句式、禁止老师腔自问自答、"
        "禁止滥用破折号与冒号、禁止编造虚假数字与伪严谨统计。\n"
    )

    user_prompt = (
        f"【小说类型】{genre}\n"
        f"【小说简介】{summary or '（暂无）'}\n\n"
        f"【本章其他已填要素】\n{ctx_block}\n\n"
        f"【当前要处理的字段】{body.field_label}\n\n"
        f"{task}\n\n"
        f"请直接输出「{body.field_label}」的成品内容："
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    adapter_config = {
        "api_base": default.api_base,
        "api_key": default.api_key,
        "model_name": default.model_name,
    }
    chat_params = {
        "temperature": 0.7,
        "top_p": default.top_p,
        "max_tokens": 1024,
        "enable_thinking": False,
    }
    # 轻量草稿也防复读拖沓：ollama 用 repeat_penalty，其余用 frequency/presence_penalty
    vendor = (default.vendor or "").lower()
    if vendor == "ollama":
        chat_params["repeat_penalty"] = 1.2
    else:
        chat_params["frequency_penalty"] = 0.3
        chat_params["presence_penalty"] = 0.2

    try:
        adapter = get_adapter(default.vendor, adapter_config)
        text = adapter.chat(messages, **chat_params)
    except Exception as e:  # noqa: BLE001
        return fail(50201, f"模型调用失败：{str(e)[:200]}")

    print(f"[polish-element] 模型原始返回（未清洗）: {text[:1000]!r}", flush=True)
    text = _strip_wrapper(text)
    if not text:
        print(f"[polish-element] 清洗后为空: vendor={vendor} model={default.model_name}", flush=True)
        return fail(50202, "模型返回为空，请重试")
    return ok({"text": text, "mode": mode})


class AggregateOverviewRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())  # 允许字段名 model_id
    model_id: Optional[str] = None   # 可选：指定聚合用模型，不传回退 memory 角色/默认模型


@router.post("/projects/{project_id}/aggregate-overview")
def aggregate_overview_endpoint(project_id: str, body: AggregateOverviewRequest,
                                db: Session = Depends(get_session)):
    """手动刷新整本概览：篇/卷/小说三级全部用 LLM 压缩（auto=False），产出精修概览。

    与章生成后的自动聚合（auto=True，仅篇级 LLM、卷/小说拼接兜底）互补：
    自动保证「永不占位」，手动按钮把整本概览升级为连贯压缩版。
    LLM 不可用时退化拼接，仍保证出内容。返回各层更新条数。
    """
    from app.services import ingestion
    try:
        agg = ingestion.aggregate_overview(db, project_id, article_id=None, auto=False,
                                           model_id=body.model_id)
        return ok({"updated": agg})
    except Exception as e:  # noqa: BLE001
        return fail(50001, f"概览聚合失败：{str(e)[:200]}")

