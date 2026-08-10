"""写作 SKILL 调度器（需求 6：让 AI 知道该调用什么 SKILL）。

原先的做法是「把所有 enabled 的 SKILL 按名称字典序全拼进去」，有两个硬伤：
1. 只有 discussion 场景有读取方，trigger=chapter/memory/parse 写了等于白写；
2. 两个风格类 SKILL 同时开启会互相打架（一个要短句，一个要长句铺陈），
   模型只能二选一，结果是随机的。

现在的规则：
- 按 trigger 过滤（目标场景 + all）；
- **互斥类**（文风/结构/视角/口吻）同类只留 priority 最高的一个——
  这类 SKILL 天然二选一，同时生效必然冲突；
- **叠加类**（禁忌/通用）全部保留——约束越多越好，不存在冲突；
- 拼接按 priority 升序，高优先级排在后面。模型对靠近末尾的指令更敏感，
  所以最重要的约束要压轴。

被互斥掉的 SKILL 会在返回值里单独列出，前端可以提示作者「你的X没生效，
因为同为文风类的Y优先级更高」，避免作者改了半天不知道为什么没效果。
"""
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.orm import CustomSkillORM

# 有效触发场景
VALID_TRIGGERS = ("discussion", "chapter", "memory", "parse", "all")

# 内置分类。互斥与否是这套调度的核心语义。
CATEGORIES = ("通用", "禁忌", "文风", "结构", "视角", "口吻")

# 这两类可以无限叠加：禁忌是约束（越多越严），通用是未分类兜底（强行互斥会误伤）
NON_EXCLUSIVE_CATEGORIES = {"通用", "禁忌"}


def _norm_category(value: str | None) -> str:
    c = (value or "").strip()
    return c if c else "通用"


def collect(db: Session, trigger: str) -> dict:
    """收集指定场景下最终生效的 SKILL。

    返回 {"active": [ORM...], "suppressed": [{"skill":ORM,"reason":str}...]}
    查询异常时返回空集合——SKILL 是增强项，绝不能因为它拖垮生成主流程。
    """
    empty = {"active": [], "suppressed": []}
    if trigger not in VALID_TRIGGERS:
        return empty
    try:
        rows = (
            db.query(CustomSkillORM)
            .filter(
                (CustomSkillORM.trigger == trigger) | (CustomSkillORM.trigger == "all")
            )
            .filter(CustomSkillORM.enabled.is_(True))
            .all()
        )
    except Exception:  # noqa: BLE001 — 表未建好 / 字段缺失时静默降级
        return empty

    candidates = [r for r in rows if (r.prompt_body or "").strip()]
    if not candidates:
        return empty

    active: list[CustomSkillORM] = []
    suppressed: list[dict] = []

    buckets: dict[str, list[CustomSkillORM]] = {}
    for r in candidates:
        buckets.setdefault(_norm_category(r.category), []).append(r)

    for category, group in buckets.items():
        if category in NON_EXCLUSIVE_CATEGORIES:
            active.extend(group)
            continue
        # 互斥：priority 最大者胜出；并列时按名称字典序取第一个，保证结果稳定可复现
        group_sorted = sorted(group, key=lambda x: (-(x.priority or 0), x.name or ""))
        winner = group_sorted[0]
        active.append(winner)
        for loser in group_sorted[1:]:
            suppressed.append({
                "skill": loser,
                "reason": (
                    f"与「{winner.name}」同属互斥分类「{category}」，"
                    f"其优先级更高（{winner.priority} > {loser.priority}），本次未生效"
                ),
            })

    # 低优先级在前、高优先级压轴
    active.sort(key=lambda x: ((x.priority or 0), x.name or ""))
    return {"active": active, "suppressed": suppressed}


def _render(skills: Iterable[CustomSkillORM]) -> str:
    blocks = []
    for o in skills:
        body = (o.prompt_body or "").strip()
        if body:
            blocks.append(f"### {o.name}\n{body}")
    return "\n\n".join(blocks)


def build_block(db: Session, trigger: str) -> str:
    """生成可直接拼进系统提示词的 SKILL 段落。无生效项时返回空串。"""
    result = collect(db, trigger)
    active = result["active"]
    if not active:
        return ""
    scene_label = {
        "chapter": "本次章节生成",
        "discussion": "本次剧情商讨",
        "memory": "本次记忆摘要",
        "parse": "本次设定解析",
    }.get(trigger, "本次任务")
    return (
        f"\n\n【写作技能合集】以下是作者为{scene_label}激活的技能，"
        "请在创作中自然遵守其指引与约束。"
        "不要向作者复述「我已加载N条技能」，按其精神执行即可：\n\n"
        + _render(active)
    )


def explain(db: Session, trigger: str) -> dict:
    """调度结果的可读说明，供前端「为什么这条技能没生效」面板使用。"""
    result = collect(db, trigger)
    return {
        "trigger": trigger,
        "active": [
            {
                "id": s.id, "name": s.name, "category": _norm_category(s.category),
                "priority": s.priority or 0, "chars": len((s.prompt_body or "").strip()),
            }
            for s in result["active"]
        ],
        "suppressed": [
            {
                "id": item["skill"].id, "name": item["skill"].name,
                "category": _norm_category(item["skill"].category),
                "priority": item["skill"].priority or 0, "reason": item["reason"],
            }
            for item in result["suppressed"]
        ],
        "total_chars": sum(len((s.prompt_body or "").strip()) for s in result["active"]),
    }
