"""上下文引擎：把散落在各张表里的创作素材，按优先级组装成模型能吃下的提示词。

原先章节生成只注入了「参考文档」一项，角色卡、势力、地点、设定库、
伏笔、商讨记录、章节记忆、写作 SKILL 全部躺在数据库里没人读。
这个包负责把它们全接上，并在超出预算时按优先级有序丢弃。
"""
from app.core.context.budget import Block, BudgetPlan, plan_budget, BUDGET_LEVELS
from app.core.context.builder import build_chapter_messages, build_discussion_system

__all__ = [
    "Block",
    "BudgetPlan",
    "plan_budget",
    "BUDGET_LEVELS",
    "build_chapter_messages",
    "build_discussion_system",
]
