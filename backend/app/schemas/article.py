"""篇（article）：4 级结构 小说→卷→篇→章 的第 3 级；篇下挂章。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ArticleBase(BaseModel):
    name: str
    summary: Optional[str] = None        # AI 生成的篇概览
    sort_order: int = 0


class ArticleCreate(ArticleBase):
    volume_id: str                       # 创建篇时必须指定所属卷


class ArticleUpdate(BaseModel):
    name: Optional[str] = None
    summary: Optional[str] = None
    sort_order: Optional[int] = None
    volume_id: Optional[str] = None      # 允许迁移篇到其他卷


class Article(ArticleBase):
    id: str
    volume_id: str
    project_id: str
    created_at: datetime
    updated_at: datetime
