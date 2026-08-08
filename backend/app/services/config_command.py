"""配置对话：把用户的自然语言设定描述，交给 LLM 抽取为结构化实体，
自动 upsert 到资料库（角色 / 势力 / 地点 / 关系网）。

流程：
1. 取默认模型配置；若无可用模型，返回友好提示（不调用 LLM）。
2. 组装 system + user 提示，要求模型只输出约定 JSON。
3. adapter.chat() 同步拿全文，剥离 ```json 围栏后解析。
4. 依次处理 characters / factions / locations（按 name upsert），
   再处理 relations（用角色姓名解析为 character id，跳过重复/无法解析）。
5. 返回 {reply, changes, model_ok}，changes 是四类实体的变更明细。
"""
import json
import math
import re

from sqlalchemy.orm import Session

from app.models.orm import CharacterORM, FactionORM, LocationORM, RelationORM
from app.schemas.database import (
    CharacterCreate, CharacterUpdate,
    FactionCreate, FactionUpdate,
    LocationCreate, LocationUpdate,
    RelationCreate,
)
from app.services import character_crud, faction_crud, location_crud, relation_crud, model_crud
from app.core.gateway.registry import get_adapter
from app.core.response import ok

SYSTEM_PROMPT = """你是一名小说设定整理助手。用户会用自然语言描述一段剧情或世界观设定，
你需要从中抽取结构化实体，并严格按照下面的 JSON 格式输出（不要输出任何多余文字、不要使用 markdown 代码块）。

{
  "reply": "用一句中文向用户说明你整理并写入了哪些设定",
  "characters": [
    {"name":"必填","role_type":"主角/配角/反派/其他","gender":"男/女/其他","age":整数或null,"personality":"性格","background":"背景","talent":"天赋","current_level":"等级/境界","brief":"一句话简介"}
  ],
  "factions": [
    {"name":"必填","description":"势力简介","status":"活跃/衰落/隐秘/其他"}
  ],
  "locations": [
    {"name":"必填","location_type":"城市/门派/秘境/洞府/其他","region":"所属区域","plane":"凡间/仙界/秘境(可自定义)","description":"描述","notable_features":["特色1","特色2"]}
  ],
  "relations": [
    {"subject":"角色A姓名","object":"角色B姓名","relation_type":"友好/敌对/亲人/师徒/上下级/暧昧/其他","strength":0到100的整数,"note":"特殊恩怨备注"}
  ]
}

规则：
- 只抽取文本中明确出现或可由上下文可靠推断的实体，不要编造。
- relations 里的 subject / object 必须是 characters 中出现过的角色姓名。
- 若文本没有可抽取的设定，返回 {"reply":"...", "characters":[], "factions":[], "locations":[], "relations":[]}。
"""

_CHAR_FIELDS = ("role_type", "gender", "age", "personality", "background",
                "talent", "current_level", "brief")
_LIST_FIELDS = ("skills", "relationship_network", "notable_features", "members")


def _as_list(v):
    """把模型可能返回的字符串/列表规范成字符串列表。"""
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [s.strip() for s in re.split(r"[，,、\n]", v) if s.strip()]
    return [str(v)]


def _extract_json(raw):
    if not raw:
        return None
    s = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
    if m:
        s = m.group(1).strip()
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(s[start:end + 1])
    except Exception:
        return None


def _empty_changes():
    return {"characters": [], "factions": [], "locations": [], "relations": []}


def run(db: Session, project_id: str, text: str, dry_run: bool = False):
    default = model_crud.get_default(db)
    use_model = default is not None and (default.status or "active") == "active"
    if not use_model:
        return ok({
            "reply": "未配置可用的默认模型。请先在左侧「模型配置」中添加模型并设为默认，才能自动整理资料库。",
            "changes": _empty_changes(),
            "model_ok": False,
        })

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    config = {
        "api_base": default.api_base,
        "api_key": default.api_key,
        "model_name": default.model_name,
        "temperature": 0.3,
        "top_p": 0.9,
        "max_tokens": 4000,
        "enable_thinking": default.enable_thinking,
    }
    try:
        adapter = get_adapter(default.vendor, config)
        raw = adapter.chat(messages, temperature=0.3)
    except Exception as e:  # noqa: BLE001
        return ok({
            "reply": f"模型调用失败：{str(e)[:200]}",
            "changes": _empty_changes(),
            "model_ok": False,
        })

    data = _extract_json(raw)
    if data is None:
        return ok({
            "reply": "AI 返回的内容无法解析为结构化设定，请换种说法或补充更多细节。",
            "changes": _empty_changes(),
            "model_ok": True,
        })

    if dry_run:
        # 预览：原样返回抽取结果，不落库
        preview = _empty_changes()
        preview["characters"] = [{"name": c.get("name"), "action": "preview"} for c in (data.get("characters") or [])]
        preview["factions"] = [{"name": c.get("name"), "action": "preview"} for c in (data.get("factions") or [])]
        preview["locations"] = [{"name": c.get("name"), "action": "preview"} for c in (data.get("locations") or [])]
        preview["relations"] = [{"subject": c.get("subject"), "object": c.get("object"), "action": "preview"} for c in (data.get("relations") or [])]
        return ok({
            "reply": data.get("reply", "（预览）以下设定将被写入资料库："),
            "changes": preview,
            "dry_run": True,
            "model_ok": True,
        })

    changes = _apply(db, project_id, data)
    return ok({
        "reply": data.get("reply", "已为你整理资料库。"),
        "changes": changes,
        "model_ok": True,
    })


def _apply(db: Session, project_id: str, data: dict):
    changes = _empty_changes()
    char_name_map = {}

    # ---- 角色 ----
    for it in (data.get("characters") or []):
        name = (it.get("name") or "").strip()
        if not name:
            continue
        existing = db.query(CharacterORM).filter_by(project_id=project_id, name=name).first()
        fields = {k: it[k] for k in _CHAR_FIELDS if k in it and it[k] not in (None, "")}
        for lf in ("skills", "relationship_network"):
            if lf in it and it[lf] is not None:
                fields[lf] = _as_list(it[lf])
        if existing:
            character_crud.update_character(db, project_id, existing.id, CharacterUpdate(**fields))
            changes["characters"].append({"id": existing.id, "name": name, "action": "updated"})
            char_name_map[name] = existing.id
        else:
            obj = character_crud.create_character(db, project_id, CharacterCreate(name=name, **fields))
            changes["characters"].append({"id": obj.id, "name": name, "action": "created"})
            char_name_map[name] = obj.id

    # ---- 势力 ----
    for it in (data.get("factions") or []):
        name = (it.get("name") or "").strip()
        if not name:
            continue
        existing = db.query(FactionORM).filter_by(project_id=project_id, name=name).first()
        fields = {}
        for k in ("description", "status"):
            if k in it and it[k] not in (None, ""):
                fields[k] = it[k]
        # 成员姓名 → 角色 id
        members = [char_name_map[m] for m in _as_list(it.get("members")) if m in char_name_map]
        if members:
            fields["members"] = members
        if existing:
            faction_crud.update_faction(db, project_id, existing.id, FactionUpdate(**fields))
            changes["factions"].append({"id": existing.id, "name": name, "action": "updated"})
        else:
            obj = faction_crud.create_faction(db, project_id, FactionCreate(name=name, **fields))
            changes["factions"].append({"id": obj.id, "name": name, "action": "created"})

    # ---- 地点（无坐标则自动散布，保证世界地图可见）----
    existing_locs = db.query(LocationORM).filter_by(project_id=project_id).all()
    base_idx = len(existing_locs)
    loc_idx = 0
    for it in (data.get("locations") or []):
        name = (it.get("name") or "").strip()
        if not name:
            continue
        existing = db.query(LocationORM).filter_by(project_id=project_id, name=name).first()
        fields = {}
        for k in ("location_type", "region", "plane", "description"):
            if k in it and it[k] not in (None, ""):
                fields[k] = it[k]
        if "notable_features" in it and it["notable_features"] is not None:
            fields["notable_features"] = _as_list(it["notable_features"])
        # 坐标：用户给就用，否则螺旋散布
        cx = it.get("center_x")
        cy = it.get("center_y")
        if cx is None or cy is None:
            ang = (base_idx + loc_idx) * 2.399963  # 黄金角，分布均匀
            r = 60 * math.sqrt(base_idx + loc_idx + 1)
            cx = round(r * math.cos(ang), 2)
            cy = round(r * math.sin(ang), 2)
            loc_idx += 1
        fields["center_x"] = cx
        fields["center_y"] = cy
        if existing:
            location_crud.update_location(db, project_id, existing.id, LocationUpdate(**fields))
            changes["locations"].append({"id": existing.id, "name": name, "action": "updated"})
        else:
            obj = location_crud.create_location(db, project_id, LocationCreate(name=name, **fields))
            changes["locations"].append({"id": obj.id, "name": name, "action": "created"})

    # ---- 关系（角色姓名 → id，跳过重复/无法解析）----
    for it in (data.get("relations") or []):
        subj = (it.get("subject") or "").strip()
        obj = (it.get("object") or "").strip()
        rtype = (it.get("relation_type") or "").strip()
        if not subj or not obj or not rtype:
            continue
        subj_id = char_name_map.get(subj)
        obj_id = char_name_map.get(obj)
        if not subj_id or not obj_id:
            changes["relations"].append({"subject": subj, "object": obj, "action": "skipped", "reason": "未找到对应角色"})
            continue
        dup = db.query(RelationORM).filter_by(
            project_id=project_id, subject_id=subj_id, object_id=obj_id
        ).first()
        if dup:
            changes["relations"].append({"subject": subj, "object": obj, "action": "skipped", "reason": "关系已存在"})
            continue
        rel = relation_crud.create_relation(db, project_id, RelationCreate(
            subject_id=subj_id,
            object_id=obj_id,
            relation_type=rtype,
            strength=int(it.get("strength", 50) or 50),
            note=it.get("note"),
        ))
        changes["relations"].append({"subject": subj, "object": obj, "id": rel.id, "action": "created"})

    return changes
