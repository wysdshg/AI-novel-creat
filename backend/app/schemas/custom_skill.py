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


class CustomSkillBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: Optional[str] = None
    prompt_body: Optional[str] = Field(None, description="注入给 AI 的提示词正文（可空）")
    trigger: Optional[str] = Field(
        "all", description=f"调用场景：{', '.join(SKILL_TRIGGERS)}"
    )
    enabled: bool = True
    tags: List[str] = Field(default_factory=list)


class CustomSkillCreate(CustomSkillBase):
    pass


class CustomSkillUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    description: Optional[str] = None
    prompt_body: Optional[str] = None
    trigger: Optional[str] = None
    enabled: Optional[bool] = None
    tags: Optional[List[str]] = None


class CustomSkill(CustomSkillBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
