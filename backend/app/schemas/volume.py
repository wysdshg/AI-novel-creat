"""卷（volume）：4 级结构 小说→卷→篇→章 的第 2 级。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class VolumeBase(BaseModel):
    name: str
    summary: Optional[str] = None        # AI 生成的卷概览
    sort_order: int = 0


class VolumeCreate(VolumeBase):
    pass


class VolumeUpdate(BaseModel):
    name: Optional[str] = None
    summary: Optional[str] = None
    sort_order: Optional[int] = None


class Volume(VolumeBase):
    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime
