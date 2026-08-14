"""全局写作 SKILL Schema。

与数据库的「技能（SkillORM，按 project 隔离，与角色绑定）」不同，
本模块是用户为 AI 加的提示词 / 技能模板，可被多个小说共享：
- discussion:  剧情商讨 / 对话阶段
- chapter:     章节生成阶段
- memory:      记忆压缩
- parse:       设定解析
- all:         全部场景
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


SKILL_TRIGGERS = ("discussion", "chapter", "memory", "parse", "all")
# 与 skill_dispatch 的互斥/叠加语义保持一致：文风/结构/视角/口吻互斥，通用/禁忌可叠加
SKILL_CATEGORIES = ("通用", "禁忌", "文风", "结构", "视角", "口吻")


class CustomSkillBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: Optional[str] = None
    prompt_body: Optional[str] = Field(None, description="注入给 AI 的提示词正文（可空）")
    trigger: Optional[str] = Field(
        "all", description=f"调用场景：{', '.join(SKILL_TRIGGERS)}"
    )
    enabled: bool = True
    tags: List[str] = Field(default_factory=list)
    # 调度控制（与 skill_dispatch 对齐）：互斥分类同类只留 priority 最高的一个；
    # 拼接按 priority 升序（高优先级更贴近指令末尾、更有效）。
    category: Optional[str] = Field(
        "通用", description=f"调度分类（互斥：{', '.join(SKILL_CATEGORIES[2:])}；可叠加：通用/禁忌）"
    )
    priority: Optional[int] = Field(
        100, ge=0, le=999, description="数值越大越优先；同分类互斥时取最大，拼接时升序"
    )


class CustomSkillCreate(CustomSkillBase):
    pass


class CustomSkillUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    description: Optional[str] = None
    prompt_body: Optional[str] = None
    trigger: Optional[str] = None
    enabled: Optional[bool] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    priority: Optional[int] = Field(None, ge=0, le=999)


class CustomSkill(CustomSkillBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
