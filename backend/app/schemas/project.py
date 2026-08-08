"""作品（项目）实体（对应 API接口规范.md §1）。"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ProjectBase(BaseModel):
    name: str = Field(..., max_length=120, description="作品名称")
    genre: Optional[str] = Field(None, description="类型：玄幻/都市/悬疑…")
    summary: Optional[str] = Field(None, description="简介")
    status: str = Field("draft", description="draft|writing|paused|finished")


class ProjectCreate(ProjectBase):
    db_backend: str = Field("sqlite", description="sqlite|mysql")


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    genre: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None


class Project(ProjectBase):
    id: str
    db_backend: str = "sqlite"
    created_at: datetime
    updated_at: datetime
    chapter_count: int = 0
