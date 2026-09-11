"""篇规划服务（Phase 7.2，2026-09-11）：「篇 = 规划单元」的落地。

流程：作者创建篇时给口述（可空）→ 检索模板 + 装配本书上下文 → LLM 出**章节级计划**
（`chapter_plan`：每章的 beat / 要点 / 新角色 / 召回角色 / 目标字数 / 章尾钩子）
→ 作者**逐行修改或 AI 只改一行**（`refine_line`）→ 拍板（`confirm`）
→ 生成时由 `layers.layer_chapter_plan` 把「本章任务」注入上下文。

三条防幻觉闸门（生成计划时）：
- `recall_chars`（召回老角色）→ 后端到 `characters` 表校验，查无此人即剔除；
- `new_chars`（引新角色）→ 只进 `planned_chars`，拍板后走既有的待确认实体机制，不直接写角色库；
- 未找到模板 → `origin="free"`（自由规划），不硬凑。

模型：DeepSeek V4.1 Flash（`thinking disabled`）—— 计划是强语义任务（升档），调用次数少。
"""
import copy
import json
import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.orm import (
    ArticlePlanORM, ArticleORM, ChapterORM,
    CharacterORM, ForeshadowORM, VolumeORM,
)
from app.services.plot_import import _ds_post, ds_key, parse_json_loose
from app.services import plot_template_crud as tpl_crud

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 上下文装配（精简版：口述 + 模板 + 卷/前情/角色/伏笔）
# ---------------------------------------------------------------------------
def _book_context(db: Session, project_id: str, article_id: str) -> dict:
    """收集规划所需的本书上下文（全部容错：缺什么跳什么）。"""
    ctx: dict = {"volume_summary": "", "prev_arc": "", "characters": [], "foreshadows": []}
    try:
        art = db.query(ArticleORM).filter_by(id=article_id).first()
        if art is not None:
            ctx["article_title"] = art.name or ""
            vol = db.query(VolumeORM).filter_by(id=art.volume_id).first() if art.volume_id else None
            if vol is not None:
                ctx["volume_summary"] = (vol.summary or "")[:500]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[plan] 卷上下文缺失: {type(e).__name__}: {e}")
    try:
        chars = db.query(CharacterORM).filter_by(project_id=project_id).limit(40).all()
        ctx["characters"] = [c.name for c in chars if c.name]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[plan] 角色上下文缺失: {type(e).__name__}: {e}")
    try:
        fos = (db.query(ForeshadowORM)
               .filter_by(project_id=project_id)
               .limit(15).all())
        ctx["foreshadows"] = [
            f"{f.description}（埋于第{f.buried_chapter or '?'}章，状态 {f.status or '—'}）"
            for f in fos if f.description
        ]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[plan] 伏笔上下文缺失: {type(e).__name__}: {e}")
    try:
        prev_ch = (db.query(ChapterORM)
                   .filter_by(project_id=project_id)
                   .order_by(ChapterORM.chapter_no.desc())
                   .first())
        if prev_ch is not None and prev_ch.content:
            ctx["prev_arc"] = (prev_ch.content or "")[-800:]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[plan] 前情上下文缺失: {type(e).__name__}: {e}")
    return ctx


def _templates_for_plan(db: Session, hint: str) -> tuple[list[dict], list[str]]:
    """按口述检索模板（top-2）；检索不可用/无结果 → 空列表（自由规划）。"""
    try:
        r = tpl_crud.search(db, query=hint or "", top_k=2)
        return r["items"], [t["id"] for t in r["items"]]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[plan] 模板检索失败: {type(e).__name__}: {e}")
        return [], []


def _plan_prompt(ctx: dict, templates: list[dict], hint: str,
                 n_chapters: int) -> str:
    t_blocks = []
    for t in templates:
        st = t.get("structure") or {}
        phases = []
        for ph in st.get("phases") or []:
            beats = "；".join(
                f"{b.get('beat')}（" + "；".join(
                    f"{v.get('src')}:{v.get('how')}" for v in (b.get("variants") or [])) + "）"
                for b in ph.get("beats") or [])
            phases.append(f"  · {ph.get('phase')}：{beats}")
        t_blocks.append(
            f"《{t['name']}》—— {t.get('logline') or ''}（节奏 {t.get('rhythm') or '—'}）\n"
            + "\n".join(phases)
            + ("\n常见翻车点：" + "；".join(t.get("pitfalls") or []) if t.get("pitfalls") else "")
        )
    t_text = "\n\n".join(t_blocks) if t_blocks else "（无匹配模板，请根据口述与上下文自由设计本篇结构）"

    ctx_lines = [
        f"篇名：{ctx.get('article_title') or '（未命名）'}",
        f"卷概要：{ctx.get('volume_summary') or '（无）'}",
        f"本书角色（可召回）：{'、'.join(ctx.get('characters') or []) or '（暂无）'}",
        f"未回收伏笔：{'；'.join(ctx.get('foreshadows') or []) or '（无）'}",
        f"最近正文结尾：…{(ctx.get('prev_arc') or '')[-400:]}",
    ]

    return (
        f"你是网文结构师。请为本篇规划**逐章计划**（共 {n_chapters} 章），"
        "每章是一个「场」：有冲突、有推进、有结尾钩子。\n\n"
        "🔴 **反抄袭铁律（最高优先级）**：下面的模板内容**只借鉴节拍结构**（冲突如何升级、"
        "爽点如何释放），**严禁照抄其表层内容**——模板原文中出现的任何人名、地名、宗门/势力名、"
        "功法/法宝/血脉名、称号与具体桥段（如某宗退婚、某玉佩传承），一律不得出现在你的计划里，"
        "必须替换为自创的、符合本书世界观的名称与设定。输出中若出现源书专名视为不合格。\n\n"
        f"作者口述（最高优先级，必须尊重）：{hint or '（未提供，参考模板与上下文设计）'}\n\n"
        f"【本书上下文】\n" + "\n".join(ctx_lines) +
        f"\n\n【候选模板（借鉴结构，不要照抄；与口述冲突时以口述为准）】\n{t_text}\n\n"
        "输出 JSON（不要 markdown 代码块、不要任何额外说明）：\n"
        '{"lines":[{"no":1,"beat":"节拍名（4~8字）","summary":"本章剧情要点（60~120字，'
        '说清冲突与结果）","new_chars":["可引新角色"],"recall_chars":["召回老角色"],'
        '"target_words":3000,"hook":"章尾钩子（15字内）","template_ref":"借鉴的模板节拍"}],'
        '"notes":"给作者的整体说明（50字内）"}'
    )


# ---------------------------------------------------------------------------
# 生成 / 修改 / 拍板
# ---------------------------------------------------------------------------
def _valid_lines(lines) -> list[dict]:
    out = []
    for x in lines or []:
        try:
            no = int(x.get("no"))
        except (TypeError, ValueError):
            continue
        if not (x.get("summary") or x.get("beat")):
            continue
        out.append({
            "no": no,
            "beat": str(x.get("beat") or "").strip(),
            "summary": str(x.get("summary") or "").strip(),
            "new_chars": [str(c) for c in (x.get("new_chars") or [])],
            "recall_chars": [str(c) for c in (x.get("recall_chars") or [])],
            "target_words": int(x.get("target_words") or 3000),
            "hook": str(x.get("hook") or "").strip(),
            "template_ref": str(x.get("template_ref") or "").strip(),
        })
    out.sort(key=lambda x: x["no"])
    return out


def generate_plan(db: Session, project_id: str, article_id: str, *,
                  hint: str = "", n_chapters: int = 8,
                  force_free: bool = False) -> dict:
    """生成本篇的章节级计划（覆盖该篇的旧 draft）。"""
    key = ds_key(db)
    if not key:
        raise RuntimeError("未配置 DeepSeek Key（app_configs.llm.deepseek_key）")

    ctx = _book_context(db, project_id, article_id)
    templates, t_ids = ([], []) if force_free else _templates_for_plan(db, hint)
    origin = "template" if templates else "free"

    raw = _ds_post(key, _plan_prompt(ctx, templates, hint, n_chapters),
                   max_tokens=6000)
    data = parse_json_loose(raw) or {}
    lines = _valid_lines(data.get("lines"))
    if not lines:
        raise RuntimeError(f"计划生成失败：模型未输出有效行；raw 前 200 字: {raw[:200]!r}")

    # 防幻觉闸门：召回角色必须在 characters 表里真实存在
    valid_names = {c.name for c in db.query(CharacterORM)
                   .filter_by(project_id=project_id).all() if c.name}
    unknown: list[str] = []
    for ln in lines:
        kept = []
        for name in ln["recall_chars"]:
            if name in valid_names:
                kept.append(name)
            else:
                unknown.append(name)
        ln["recall_chars"] = kept
    if unknown:
        logger.warning(f"[plan] 召回角色查无此人（已剔除）: {unknown}")

    # 同一篇只保留一条当前计划：旧 draft 直接覆盖；confirmed 的会归档进 raw_ai 历史
    old = (db.query(ArticlePlanORM)
           .filter_by(project_id=project_id, article_id=article_id)
           .order_by(ArticlePlanORM.updated_at.desc()).first())
    raw_ai = {"last": raw}
    if old is not None and old.status == "confirmed":
        hist = (old.raw_ai or {}).get("history") or []
        hist.append({"plan": old.plan, "archived_at": datetime.utcnow().isoformat()})
        raw_ai["history"] = hist[-5:]

    if old is not None:
        old.template_ids = t_ids
        old.template_names = [t["name"] for t in templates]
        old.plan = {"lines": lines, "notes": str(data.get("notes") or "")}
        old.origin = origin
        old.raw_ai = raw_ai
        old.status = "draft"
        old.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(old)
        return {"plan_id": old.id, "lines": len(lines), "unknown_chars": unknown,
                "templates": [t["name"] for t in templates]}

    o = ArticlePlanORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        article_id=article_id,
        template_ids=t_ids,
        template_names=[t["name"] for t in templates],
        plan={"lines": lines, "notes": str(data.get("notes") or "")},
        origin=origin,
        raw_ai=raw_ai,
        status="draft",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return {"plan_id": o.id, "lines": len(lines), "unknown_chars": unknown,
            "templates": [t["name"] for t in templates]}


def refine_line(db: Session, project_id: str, article_id: str, *,
                line_no: int, instruction: str) -> dict:
    """AI 只改一行（行级局部修改）：其余行原样保留。"""
    key = ds_key(db)
    if not key:
        raise RuntimeError("未配置 DeepSeek Key（app_configs.llm.deepseek_key）")
    plan = (db.query(ArticlePlanORM)
            .filter_by(project_id=project_id, article_id=article_id)
            .order_by(ArticlePlanORM.updated_at.desc()).first())
    if plan is None:
        raise RuntimeError("该篇还没有计划（先跑 --stage plan 或调生成接口）")
    # ⚠️ 这里必须 deep copy：直接拿 plan.plan["lines"] 会拿到**同一个列表对象**，
    # 后续对 lines 的任何修改都会同步"污染"SQLAlchemy 记住的旧值 ——
    # 赋新值时 new==old，UPDATE 被跳过（2026-09-11 实测踩坑，refine 返回正确但库纹丝不动）。
    lines = copy.deepcopy((plan.plan or {}).get("lines") or [])
    target = next((x for x in lines if int(x.get("no") or 0) == int(line_no)), None)
    if target is None:
        raise RuntimeError(f"计划里没有第 {line_no} 行")
    neighbors = [x for x in lines if x is not target]
    prompt = (
        f"这是本篇的章节计划，需要修改第 {line_no} 行（只改这一行，输出**修改后的完整 JSON 行**）。\n"
        f"修改要求：{instruction}\n\n"
        f"【当前这一行】\n{json.dumps(target, ensure_ascii=False)}\n"
        f"【上下文（只读参考，不要输出）】\n"
        + json.dumps(neighbors[:6], ensure_ascii=False)[:1500]
        + "\n\n输出 JSON（单行对象，字段与输入相同）："
    )
    raw = _ds_post(key, prompt, max_tokens=800)
    data = parse_json_loose(raw) or {}
    data.setdefault("no", line_no)
    fixed = _valid_lines([data])
    if not fixed:
        raise RuntimeError(f"改行失败：模型输出无效；raw 前 150 字: {raw[:150]!r}")
    new_line = fixed[0]
    new_line["no"] = line_no
    for i, x in enumerate(lines):
        if int(x.get("no") or 0) == int(line_no):
            lines[i] = new_line
            break
    # ⚠️ 深拷贝：lines 与 plan.plan["lines"] 是**同一个列表对象**，SQLAlchemy 对 JSON 列
    # 用值比较判断是否 dirty —— 不拷贝的话新值==旧值（共享列表已同步变化），UPDATE 会被跳过
    # （2026-09-11 实测踩坑：refine 返回正确但库纹丝不动）。
    plan.plan = copy.deepcopy({"lines": lines, "notes": (plan.plan or {}).get("notes") or ""})
    plan.updated_at = datetime.utcnow()
    db.commit()
    return {"line": new_line, "origin": plan.origin}


def confirm_plan(db: Session, project_id: str, article_id: str) -> dict:
    """作者拍板：draft → confirmed（此后生成会注入本章任务）。"""
    plan = (db.query(ArticlePlanORM)
            .filter_by(project_id=project_id, article_id=article_id)
            .order_by(ArticlePlanORM.updated_at.desc()).first())
    if plan is None:
        raise RuntimeError("该篇还没有计划")
    plan.status = "confirmed"
    plan.updated_at = datetime.utcnow()
    db.commit()
    return {"plan_id": plan.id, "status": plan.status, "lines": len((plan.plan or {}).get("lines") or [])}


def get_plan(db: Session, project_id: str, article_id: str) -> dict | None:
    """取当前计划（含行列表）。"""
    plan = (db.query(ArticlePlanORM)
            .filter_by(project_id=project_id, article_id=article_id)
            .order_by(ArticlePlanORM.updated_at.desc()).first())
    if plan is None:
        return None
    lines = (plan.plan or {}).get("lines") or []
    return {
        "id": plan.id,
        "project_id": plan.project_id,
        "article_id": plan.article_id,
        "template_ids": plan.template_ids or [],
        "template_names": plan.template_names or [],
        "origin": plan.origin,
        "status": plan.status,
        "notes": (plan.plan or {}).get("notes") or "",
        "lines": lines,
    }


def save_lines(db: Session, project_id: str, article_id: str, *,
               lines: list[dict], notes: str | None = None) -> dict:
    """作者在表格里改完提交（行级编辑的保存动作）。"""
    plan = (db.query(ArticlePlanORM)
            .filter_by(project_id=project_id, article_id=article_id)
            .order_by(ArticlePlanORM.updated_at.desc()).first())
    if plan is None:
        raise RuntimeError("该篇还没有计划")
    fixed = _valid_lines(lines)
    # 同 refine_line：深拷贝断开与旧 JSON 值的共享引用（否则 UPDATE 被跳过）
    plan.plan = copy.deepcopy(
        {"lines": fixed, "notes": notes if notes is not None else (plan.plan or {}).get("notes") or ""})
    plan.updated_at = datetime.utcnow()
    db.commit()
    return {"plan_id": plan.id, "lines": len(fixed)}


def upsert_draft_for_article(db: Session, project_id: str, article_id: str) -> dict:
    """确认前校验：篇必须存在。"""
    art = db.query(ArticleORM).filter_by(id=article_id).first()
    if art is None:
        raise RuntimeError("篇不存在")
    return {"article_id": art.id, "name": art.name}
