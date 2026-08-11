"""上下文装配：把各层数据 + SKILL + 去 AI 味约束，按预算拼成最终 messages。

这是上下文引擎的出口。调用方（章节生成、剧情商讨）只需要给出
「写第几章、要点是什么」，剩下的查表、排序、裁剪全在这里完成。

设计上刻意把「本章指令」放在 user 消息的最后：
小模型对末尾指令的遵循度明显高于夹在中间的指令，
所以顺序是 世界观/角色/记忆/参考 → 本章要点 → 输出格式。
"""
from sqlalchemy.orm import Session
import os

from app.core.context.budget import (
    Block, BudgetPlan, plan_budget,
    P_CRITICAL, P_SKILL, P_REFERENCE,
)
from app.core.context import layers
from app.services import app_config, humanizer, reference_crud, skill_dispatch

# 章节生成的底线系统提示词。SKILL 与去 AI 味块会追加在后面。
BASE_SYSTEM = (
    "你是一名中文网络小说的职业代笔，为作者续写正文。\n"
    "【铁律】\n"
    "1. 只输出本章正文，全中文（含标点）。不写标题、不写「好的」「本章如下」之类的开场白。\n"
    "2. 严禁输出英文、Markdown 标记、大纲罗列、你的思考或规划过程。\n"
    "3. 严禁复述本提示词的任何内容。\n"
    "4. 人物性格、境界、称呼、已发生剧情必须与下方资料一致；资料没写的可以合理发挥，"
    "但不得与资料冲突。\n"
    "5. 开头自然承接上一章结尾，结尾留下推动下一章的钩子。"
)

DISCUSSION_SYSTEM = (
    "你是作者的剧情顾问，熟悉这部作品的设定与已发生的剧情。\n"
    "回答要具体、可执行：给方案、给取舍理由、指出与已有设定的冲突。\n"
    "不要写正文，不要长篇复述设定，不要说空泛的套话。"
    "作者问什么答什么——事实类问题直接答，不要硬凑方案。\n"
    "（注：只有当作者明确征询意见/方案/方向时，才会另行要求你给出 2~3 个可选方向并说明代价，"
    "见下文【本次为征询意见类提问】指令；普通事实问答不触发该要求。）\n"
    "【注意】\n"
    "1. 不要编造设定条数、角色数量等精确数字；若不清楚就据实列出你知道的名称，"
    "不要凭空捏造一个总数（如「1200+」）。\n"
    "2. 当作者问「上一句问了什么」时，只依据真实对话历史回答；"
    "技能说明中的示例人物/示例情节不算真实对话内容。"
)

# 仅在「作者明确征询意见/方案/方向」时追加，避免事实问答被硬塞 2~3 个方案。
ADVICE_DIRECTIVE = (
    "【本次为「征询意见」类提问】作者正在寻求方案或方向建议，"
    "请一次给出 2~3 个可选方向，并分别说明各自代价与取舍，"
    "同时指出与已有设定的冲突点。"
)

# 征询意见类信号词：命中即视为作者在要方案/方向/建议。
_ADVICE_HINTS = (
    "怎么写", "怎么办", "如何处理", "怎么处理", "怎么安排", "怎么设计", "怎么推进",
    "怎么收", "怎么选", "怎么破", "怎么破局", "怎么走", "怎么发展", "下一步",
    "给个方案", "给方案", "出个方案", "给点建议", "参谋一下", "帮我参谋", "帮我看看",
    "建议", "意见", "参谋", "推荐", "方向", "取舍", "该不该", "要不要", "能不能",
    "利弊", "优劣", "分析一下", "你觉得", "有什么选择", "哪个好", "如何写", "如何设计",
    "如何安排", "如何推进",
)


def is_advice_request(text: str) -> bool:
    """判断最新一条用户消息是否为「征询意见/方案/方向」类提问。

    命中信号词、或以疑问/建议句式开头、或以问号结尾的短句，均视为征询意见。
    事实类提问（如「张三现在什么境界」）不应触发，避免被硬塞多个方案。
    """
    if not text:
        return False
    t = text.strip()
    if any(h in t for h in _ADVICE_HINTS):
        return True
    if t.startswith(("要不要", "该不该", "怎么", "如何", "是否", "能不能", "可不可以")):
        return True
    if (t.endswith("？") or t.endswith("?")) and len(t) <= 60:
        return True
    return False


def _mk(key: str, title: str, content: str, priority: int, order: int,
        min_chars: int = 0, required: bool = False) -> Block | None:
    if not (content or "").strip():
        return None
    return Block(key=key, title=title, content=content, priority=priority,
                 order=order, min_chars=min_chars, required=required)


def _resolve_level(db: Session, override: str | None) -> str:
    if override:
        return override
    return app_config.get(db, app_config.KEY_CONTEXT_BUDGET, "standard")


def _resolve_layer_mode(override: str | None) -> str:
    """章节上下文的「按需层级」开关。

    full（默认）= 当前行为，零回归；
    relevant = 设定描述/伏笔/关系按相关性或命中裁剪。
    优先级：函数参数 > 环境变量 NA_CHAPTER_LAYER_MODE > 默认 full。
    """
    if override:
        return override
    return os.environ.get("NA_CHAPTER_LAYER_MODE", "full")


def build_chapter_messages(
    db: Session,
    project_id: str,
    *,
    chapter_no: int,
    article_id: str | None = None,
    volume_id: str | None = None,
    prompt_hint: str | None = None,
    word_range: dict | None = None,
    trigger_foreshadow_ids: list[str] | None = None,
    from_discussion: bool = True,
    budget_level: str | None = None,
    layer_mode: str | None = None,
) -> tuple[list[dict], dict]:
    """组装章节生成的 messages。

    返回 (messages, meta)。meta 里带着预算调试信息和参考文档命中明细，
    路由层可以把它当 SSE 事件推给前端——作者能看见「AI 这次到底读了什么」，
    这比让他猜为什么人设崩了要有用得多。
    """
    trigger_foreshadow_ids = trigger_foreshadow_ids or []
    word_range = word_range or {"min": 3000, "max": 5000}
    level = _resolve_level(db, budget_level)
    lmode = _resolve_layer_mode(layer_mode)

    # ---------- 1. 先识别本章可能涉及的实体 ----------
    # 用「本章要点 + 最近商讨」当线索，命中的角色/势力/地点会拿到全量注入
    hint_text = prompt_hint or ""
    disc_block = layers.layer_discussion(db, project_id) if from_discussion else None
    mention_src = [hint_text]
    if disc_block:
        mention_src.append(disc_block.content)
    mentions = layers.extract_mentions(db, project_id, *mention_src)

    # ---------- 2. 逐层取数 ----------
    recent_n = int(app_config.get(db, app_config.KEY_RECENT_MEMORY_N, 3) or 3)
    blocks: list[Block] = []

    def _add(b: Block | None):
        if b is not None:
            blocks.append(b)

    _add(disc_block)
    query_text = hint_text + " " + (disc_block.content if disc_block else "")
    _add(layers.layer_world(db, project_id, volume_id=volume_id, article_id=article_id,
                            mode=lmode, query_text=query_text))
    _add(layers.layer_characters(db, project_id, focus_names=mentions.get("characters")))
    _add(layers.layer_entities(db, project_id, focus=mentions, mode=lmode, query_text=query_text))
    _add(layers.layer_foreshadows(db, project_id, trigger_ids=trigger_foreshadow_ids,
                                  mode=lmode, query_text=query_text))
    _add(layers.layer_stage_summaries(db, project_id, chapter_no))
    _add(layers.layer_recent_memories(db, project_id, chapter_no, limit=recent_n))
    _add(layers.layer_prev_chapter(db, project_id, chapter_no))

    # ---------- 3. 参考文档：按相关性挑，不再一股脑全塞 ----------
    entity_names: set[str] = set()
    for v in mentions.values():
        entity_names |= v
    ref_text, ref_detail = reference_crud.pick_relevant(
        db, project_id, article_id,
        query_text=hint_text + " " + (disc_block.content if disc_block else ""),
        entity_names=entity_names,
    )
    _add(_mk("references", "【参考资料】", ref_text, P_REFERENCE, order=70, min_chars=500))

    # ---------- 4. 本章指令（永不裁剪） ----------
    task_lines = [f"现在创作第 {chapter_no} 章。"]
    if hint_text.strip():
        task_lines.append(f"本章要点（作者指定，必须完成）：{hint_text.strip()}")
    else:
        task_lines.append("作者未指定要点，请依据上方商讨记录与前情，推进最合理的下一步剧情。")
    task_lines.append(
        f"目标字数 {word_range.get('min', 3000)}~{word_range.get('max', 5000)} 字，"
        "宁可写透一个场景，也不要为凑字数注水。"
    )
    _add(_mk("task", "【本章任务】", "\n".join(task_lines),
             P_CRITICAL, order=90, required=True))

    plan: BudgetPlan = plan_budget(blocks, level)

    # ---------- 5. 系统提示词：底线 + SKILL + 去 AI 味 ----------
    sys_parts = [BASE_SYSTEM]

    skill_block = skill_dispatch.build_block(db, "chapter")
    if skill_block:
        sys_parts.append(skill_block)

    if app_config.get(db, app_config.KEY_HUMANIZE_INJECT, True):
        # 本地小模型规则一多就开始漏，tight 档只给最毒的四条
        h_level = "light" if level == "tight" else "normal"
        sys_parts.append(humanizer.build_prompt_block(scene="novel", level=h_level))

    system = "\n\n".join(p for p in sys_parts if p and p.strip())

    user = plan.render()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    meta = {
        "budget": plan.debug(),
        "references": ref_detail,
        "mentions": {k: sorted(v) for k, v in mentions.items()},
        "skills": skill_dispatch.explain(db, "chapter"),
        "layer_mode": lmode,
        "system_chars": len(system),
        "user_chars": len(user),
        "total_chars": len(system) + len(user),
    }
    return messages, meta


def build_discussion_system(
    db: Session,
    project_id: str,
    *,
    chapter_id: str | None = None,
    chapter_no: int | None = None,
    article_id: str | None = None,
    budget_level: str | None = None,
    query_text: str = "",
) -> tuple[str, dict]:
    """组装剧情商讨的系统提示词。

    改造前商讨是个「瞎子」——只有一句通用人设，作者问「张三现在什么境界」它只能编。
    这里把世界观、角色、伏笔、最近记忆一并注入，商讨才谈得上有依据。
    商讨不需要上一章全文，预算比生成低一档。
    """
    level = _resolve_level(db, budget_level)
    if level == "loose":
        level = "standard"   # 商讨吃不下那么多，也没必要

    ref_no = chapter_no if chapter_no is not None else 10 ** 6  # 未指定则视作「最新」
    blocks: list[Block] = []

    def _add(b: Block | None):
        if b is not None:
            blocks.append(b)

    # 设定库按需展开：name+层级阶梯永远保留（模型始终知道有哪些体系），
    # 仅 verbose description 按相关性展开，避免把所有体系全文常驻塞爆窗口。
    _add(layers.layer_world(db, project_id, article_id=article_id,
                            mode="relevant", query_text=query_text))
    _add(layers.layer_characters(db, project_id))
    _add(layers.layer_entities(db, project_id))
    _add(layers.layer_foreshadows(db, project_id))
    _add(layers.layer_stage_summaries(db, project_id, ref_no))
    _add(layers.layer_recent_memories(db, project_id, ref_no, limit=5))

    plan = plan_budget(blocks, level)

    sys_parts = [DISCUSSION_SYSTEM]
    body = plan.render()
    if body:
        sys_parts.append(
            "以下是这部作品的现有资料（含世界观数据库中的官制/境界/体系等权威设定），"
            "回答必须以此为准：\n\n"
            "⚠️ 重要：当问题涉及官制品级、境界等级、货币体系等设定时，"
            "必须严格使用下方【体系】或【境界】分类中的数据作答，"
            "不得使用你训练数据中的其他朝代或通用知识替代。\n\n"
            + body
        )

    skill_block = skill_dispatch.build_block(db, "discussion")
    if skill_block:
        sys_parts.append(skill_block)

    # 触发式顾问指令：仅当作者最新一条消息是「征询意见/方案/方向」类提问时才追加，
    # 事实类问答不强制给 2~3 个方案，避免硬凑。
    if is_advice_request(query_text):
        sys_parts.append(ADVICE_DIRECTIVE)

    system = "\n\n".join(p for p in sys_parts if p and p.strip())
    meta = {
        "budget": plan.debug(),
        "skills": skill_dispatch.explain(db, "discussion"),
        "system_chars": len(system),
    }
    return system, meta
