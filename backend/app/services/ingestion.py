"""写后摄取：一章写完之后，自动把它变成「结构化记忆」。

这是需求 1（AI 写数据库）和需求 4（章后给走向建议）的落点。

为什么不在生成时同步做：生成已经是流式长任务，再串一次抽取会让作者干等。
所以摄取放在正文落库之后单独跑，失败也只影响记忆，不影响正文。

抽取失败的兜底很关键——本地 4B 输出 JSON 的成功率大概八成。
剩下两成如果直接放弃，记忆表就会出现空洞，下一章读不到前情。
所以准备了规则兜底：正文首尾截取 + 已登记实体子串匹配，
质量不如模型抽取，但保证「记忆链不断」。
"""
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.context import layers
from app.core.gateway.registry import get_adapter
from app.models.orm import ChapterORM
from app.services import (
    app_config, discussion_crud, memory_crud, model_crud,
    reference_crud, skill_dispatch,
)

# 摄取用的抽取指令。刻意用「填空题」形式而不是开放描述——
# 4B 模型对「照着模板填」的遵循度远高于「请你总结一下」。
EXTRACT_SYSTEM = (
    "你是小说编辑助手，负责把一章正文压缩成结构化档案。\n"
    "只输出一个 JSON 对象，不要输出任何解释、前言、Markdown 代码块标记。\n"
    "所有字段都必须用中文填写。字段说明：\n"
    '{\n'
    '  "summary": "本章剧情摘要，150~250字，只写发生了什么，不要评价",\n'
    '  "ending_hook": "本章结尾停在哪里、留下什么悬念，一句话",\n'
    '  "characters": ["本章出场的角色名"],\n'
    '  "locations": ["本章出现的地点名"],\n'
    '  "plot_points": ["关键事件，3~5条，每条一句话"],\n'
    '  "foreshadow_actions": [{"action": "bury/hint/resolve", "desc": "涉及的伏笔"}],\n'
    '  "new_entities": [{"kind": "character/faction/location", "name": "名称", '
    '"brief": "一句话说明"}],\n'
    '  "next_directions": [{"title": "走向标题", "detail": "具体怎么写，两三句", '
    '"tension": "高/中/低"}]\n'
    '}\n'
    "next_directions 给 3 条，要求方向彼此不同（不要三条都是打一架），"
    "并且必须能从本章结尾自然接上。\n"
    "new_entities 只填本章新出现、且资料里没有的；没有就给空数组。"
)

_JSON_KEYS = (
    "summary", "ending_hook", "characters", "locations",
    "plot_points", "foreshadow_actions", "new_entities", "next_directions",
)


# ===========================================================================
# JSON 抽取容错
# ===========================================================================

def parse_json_loose(text: str) -> dict | None:
    """从模型输出里把 JSON 抠出来。

    实测本地小模型常见的四种脏输出：包在 ```json 里、前面带一句「好的」、
    结尾多个逗号、以及中文全角引号。这里逐个处理，能救一个是一个。
    """
    if not text:
        return None
    s = text.strip()

    # 去掉代码块围栏
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)

    # 取第一个 { 到最后一个 } 之间
    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1 or j <= i:
        return None
    body = s[i:j + 1]

    for attempt in range(3):
        try:
            data = json.loads(body)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            if attempt == 0:
                # 尾逗号
                body = re.sub(r",\s*([}\]])", r"\1", body)
            elif attempt == 1:
                # 全角引号 → 半角（只换成对出现的）
                body = body.replace("“", '"').replace("”", '"')
            else:
                return None
    return None


def _as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        parts = [p.strip() for p in re.split(r"[；;\n]", v) if p.strip()]
        return parts
    return [v]


def normalize_extract(data: dict) -> dict:
    """把模型可能给歪的结构掰回标准形状。"""
    out: dict[str, Any] = {}
    out["summary"] = str(data.get("summary") or "").strip()
    out["ending_hook"] = str(data.get("ending_hook") or "").strip()
    out["characters"] = [str(x).strip() for x in _as_list(data.get("characters")) if str(x).strip()]
    out["locations"] = [str(x).strip() for x in _as_list(data.get("locations")) if str(x).strip()]
    out["plot_points"] = [str(x).strip() for x in _as_list(data.get("plot_points")) if str(x).strip()][:6]

    fa = []
    for item in _as_list(data.get("foreshadow_actions")):
        if isinstance(item, dict):
            desc = str(item.get("desc") or item.get("description") or "").strip()
            act = str(item.get("action") or "hint").strip()
            if desc:
                fa.append({"action": act, "desc": desc})
        elif str(item).strip():
            fa.append({"action": "hint", "desc": str(item).strip()})
    out["foreshadow_actions"] = fa[:8]

    ne = []
    for item in _as_list(data.get("new_entities")):
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                ne.append({
                    "kind": str(item.get("kind") or "character").strip(),
                    "name": name,
                    "brief": str(item.get("brief") or "").strip(),
                })
    out["new_entities"] = ne[:10]

    nd = []
    for item in _as_list(data.get("next_directions")):
        if isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            detail = str(item.get("detail") or "").strip()
            if title or detail:
                nd.append({
                    "title": title or detail[:20],
                    "detail": detail,
                    "tension": str(item.get("tension") or "中").strip(),
                })
        elif str(item).strip():
            nd.append({"title": str(item).strip()[:20], "detail": str(item).strip(), "tension": "中"})
    out["next_directions"] = nd[:5]
    return out


def fallback_extract(db: Session, project_id: str, content: str) -> dict:
    """模型不可用或解析失败时的规则兜底。

    摘要用首段 + 尾段拼（开头交代场景、结尾是钩子，中间过程可以省），
    出场实体用资料库已登记名做子串匹配。粗，但不会断链。
    """
    body = (content or "").strip()
    paras = [p.strip() for p in body.split("\n") if p.strip()]
    head = "".join(paras[:2])[:180] if paras else ""
    tail = "".join(paras[-2:])[-160:] if paras else ""
    summary = (head + ("……" if head and tail else "") + tail).strip()

    mentions = layers.extract_mentions(db, project_id, body)
    return {
        "summary": summary or "（本章摘要抽取失败，以下为空档，可点重新摄取）",
        "ending_hook": tail[-80:] if tail else "",
        "characters": sorted(mentions.get("characters", set())),
        "locations": sorted(mentions.get("locations", set())),
        "plot_points": [],
        "foreshadow_actions": [],
        "new_entities": [],
        "next_directions": [],
        "_fallback": True,
    }


# ===========================================================================
# 模型选择
# ===========================================================================

def _pick_model(db: Session):
    """优先用 role='memory' 的模型（抽取任务可以用更小更快的），否则用默认模型。"""
    from app.models.orm import ModelConfigORM
    try:
        m = (
            db.query(ModelConfigORM)
            .filter(ModelConfigORM.role == "memory")
            .filter(ModelConfigORM.status == "active")
            .first()
        )
        if m:
            return m
    except Exception:  # noqa: BLE001
        pass
    d = model_crud.get_default(db)
    if d is not None and (d.status or "active") == "active":
        return d
    return None


def _model_config(m) -> dict:
    return {
        "api_base": m.api_base,
        "api_key": m.api_key,
        "model_name": m.model_name,
        "temperature": 0.2,          # 抽取是信息任务，温度必须压低
        "top_p": m.top_p,
        "max_tokens": min(m.max_tokens or 2000, 2000),
        "enable_thinking": False,    # 思考过程会污染 JSON 输出
    }


# ===========================================================================
# 主入口
# ===========================================================================

def ingest_chapter(
    db: Session,
    project_id: str,
    chapter: ChapterORM,
    push_directions: bool | None = None,
) -> dict:
    """一章写完后的全部收尾动作。

    顺序：抽记忆 → 落库 → 写篇章摘要（给参考文档）→ 推走向卡片到对话区
    → 够章数就压阶段摘要。

    每步独立 try，前一步失败不阻断后一步——记忆抽歪了不该导致摘要也不写。
    """
    result: dict[str, Any] = {"chapter_id": chapter.id, "chapter_no": chapter.chapter_no}
    content = (chapter.content or "").strip()
    if not content:
        result["skipped"] = "章节正文为空"
        return result

    # ---------- 1. 抽取 ----------
    extracted: dict | None = None
    raw_out = None
    m = _pick_model(db)
    if m is not None:
        sys_parts = [EXTRACT_SYSTEM]
        skill_block = skill_dispatch.build_block(db, "memory")
        if skill_block:
            sys_parts.append(skill_block)
        # 超长正文截首尾，中间大段打斗描写对抽取贡献有限
        clip = content if len(content) <= 8000 else content[:5000] + "\n…（中略）…\n" + content[-3000:]
        messages = [
            {"role": "system", "content": "\n\n".join(sys_parts)},
            {"role": "user", "content": f"第{chapter.chapter_no}章 {chapter.title or ''}\n\n{clip}"},
        ]
        try:
            adapter = get_adapter(m.vendor, _model_config(m))
            raw_out = adapter.chat(messages)
            parsed = parse_json_loose(raw_out or "")
            if parsed:
                extracted = normalize_extract(parsed)
                if not extracted.get("summary"):
                    extracted = None  # 摘要都空，等于没抽出来
        except Exception as e:  # noqa: BLE001
            print(f"[ingestion] 记忆抽取调用失败: {type(e).__name__}: {str(e)[:150]}")

    used_fallback = extracted is None
    if used_fallback:
        extracted = fallback_extract(db, project_id, content)
    result["fallback"] = used_fallback

    # ---------- 2. 落库 ----------
    try:
        mem = memory_crud.upsert_chapter_memory(
            db, project_id, chapter.id,
            {
                **extracted,
                "article_id": chapter.article_id,
                "chapter_no": chapter.chapter_no,
                "title": chapter.title,
                "status": "pending" if extracted.get("new_entities") else "confirmed",
                "raw": (raw_out or "")[:4000] if used_fallback else None,
            },
        )
        result["memory_id"] = mem.id
        result["summary"] = mem.summary
        result["new_entities"] = mem.new_entities or []
        result["next_directions"] = mem.next_directions or []
    except Exception as e:  # noqa: BLE001
        print(f"[ingestion] 记忆落库失败: {e}")
        result["memory_error"] = str(e)[:200]

    # ---------- 3. 篇章摘要写进参考文档（追加，不覆盖） ----------
    if chapter.article_id:
        try:
            digest_lines = [extracted.get("summary", "")]
            if extracted.get("plot_points"):
                digest_lines.append("关键事件：" + "；".join(extracted["plot_points"]))
            if extracted.get("ending_hook"):
                digest_lines.append("结尾：" + extracted["ending_hook"])
            reference_crud.append_article_digest(
                db, project_id, chapter.article_id,
                chapter_no=chapter.chapter_no,
                title=chapter.title or f"第{chapter.chapter_no}章",
                digest="\n".join(x for x in digest_lines if x),
            )
            result["digest_written"] = True
        except Exception as e:  # noqa: BLE001
            print(f"[ingestion] 写篇章摘要失败: {e}")

    # ---------- 4. 走向卡片推送到对话区 ----------
    if push_directions is None:
        push_directions = bool(app_config.get(db, app_config.KEY_PUSH_DIRECTIONS, True))
    dirs = extracted.get("next_directions") or []
    if push_directions and dirs:
        try:
            body = _render_directions(chapter.chapter_no, dirs)
            discussion_crud.add_message(
                db, project_id, role="assistant", content=body,
                meta={
                    "type": "post_chapter_directions",
                    "chapter_id": chapter.id,
                    "chapter_no": chapter.chapter_no,
                    "directions": dirs,
                },
            )
            result["directions_pushed"] = len(dirs)
        except Exception as e:  # noqa: BLE001
            print(f"[ingestion] 推送走向卡片失败: {e}")

    # ---------- 5. 阶段压缩 ----------
    try:
        every = int(app_config.get(db, app_config.KEY_STAGE_EVERY, 10) or 10)
        rng = memory_crud.find_uncompressed_range(db, project_id, every)
        if rng:
            s = compress_stage(db, project_id, rng[0], rng[1])
            if s:
                result["stage_compressed"] = {"from": rng[0], "to": rng[1]}
    except Exception as e:  # noqa: BLE001
        print(f"[ingestion] 阶段压缩失败: {e}")

    return result


def _render_directions(chapter_no: int, dirs: list[dict]) -> str:
    lines = [f"第{chapter_no}章写完了。接下来我看到三条路可以走："]
    for i, d in enumerate(dirs, 1):
        t = d.get("title") or ""
        detail = d.get("detail") or ""
        tension = d.get("tension") or ""
        lines.append(f"\n{i}. {t}（张力{tension}）\n   {detail}")
    lines.append("\n想走哪条直接说，也可以让我换几个方向。")
    return "\n".join(lines)


# ===========================================================================
# 阶段摘要压缩
# ===========================================================================

STAGE_SYSTEM = (
    "你是小说编辑，把连续若干章的档案压成一段阶段脉络。\n"
    "只输出 JSON，不要解释：\n"
    '{"summary": "这一阶段的主线进展，200~300字", '
    '"key_events": ["改变格局的事件，3~6条"], '
    '"open_threads": ["到此仍未收束的线索"]}'
)


def compress_stage(db: Session, project_id: str, from_no: int, to_no: int) -> dict | None:
    """把 [from_no, to_no] 的章级记忆压成一条阶段摘要。"""
    rows = [
        r for r in memory_crud.list_chapter_memories(db, project_id)
        if from_no <= r.chapter_no <= to_no
    ]
    if not rows:
        return None
    rows.sort(key=lambda r: r.chapter_no)

    material_lines = []
    for r in rows:
        material_lines.append(f"第{r.chapter_no}章 {r.title or ''}：{r.summary or ''}")
        if r.plot_points:
            material_lines.append("  事件：" + "；".join(str(p) for p in r.plot_points))
    material = "\n".join(material_lines)

    data = None
    m = _pick_model(db)
    if m is not None:
        try:
            adapter = get_adapter(m.vendor, _model_config(m))
            out = adapter.chat([
                {"role": "system", "content": STAGE_SYSTEM},
                {"role": "user", "content": material[:12000]},
            ])
            data = parse_json_loose(out or "")
        except Exception as e:  # noqa: BLE001
            print(f"[ingestion.compress_stage] 模型调用失败: {str(e)[:150]}")

    if not data or not str(data.get("summary") or "").strip():
        # 兜底：直接把各章摘要串起来截断，信息密度低但不丢链
        data = {
            "summary": "；".join((r.summary or "")[:60] for r in rows)[:600],
            "key_events": [],
            "open_threads": [],
        }

    o = memory_crud.upsert_stage_summary(
        db, project_id, from_no, to_no,
        summary=str(data.get("summary") or "").strip(),
        key_events=[str(x) for x in _as_list(data.get("key_events"))][:8],
        open_threads=[str(x) for x in _as_list(data.get("open_threads"))][:8],
        scope="range",
    )
    return memory_crud.stage_to_dict(o)
