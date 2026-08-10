"""全局设定库（境界修为 / 货币 / 体系 / 规则 …）的 Pydantic Schema。

设计为全局共享资源，多本小说可复用同一套设定（创建小说时让用户挑选）。
所有端点不要求 project_id。
"""
from datetime import datetime
from typing import Optional, List, Any

from pydantic import BaseModel, Field


SETTING_CATEGORIES = ("境界", "货币", "体系", "规则", "其它")


class SettingBase(BaseModel):
    """设定通用字段。"""
    name: str = Field(..., min_length=1, max_length=120, description="设定名")
    category: str = Field("其它", description=f"分类，可选：{', '.join(SETTING_CATEGORIES)}")
    levels: List[Any] = Field(default_factory=list, description="等级/条目 JSON 数组")
    description: Optional[str] = Field(None, description="详细说明")
    tags: List[str] = Field(default_factory=list, description="检索关键词")
    is_template: bool = Field(False, description="是否可被新建小说时挑选的模板")


class SettingCreate(SettingBase):
    pass


class SettingUpdate(BaseModel):
    """全字段可空；空值表示不修改。"""
    name: Optional[str] = Field(None, max_length=120)
    category: Optional[str] = None
    levels: Optional[List[Any]] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    is_template: Optional[bool] = None


class Setting(SettingBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
