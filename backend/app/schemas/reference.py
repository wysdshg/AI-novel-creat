"""参考文档 schema（每本小说可手动上传，供 AI 生成时参考读取）。

列表接口返回不带正文的摘要（避免大负载），详情/上传接口携带正文。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ReferenceDocCreate(BaseModel):
    filename: str = Field(..., min_length=1, max_length=200)
    content_type: str = "text/plain"
    size: int = 0
    content_text: str = Field(default="", description="文件文本正文")


class ReferenceDocSummary(BaseModel):
    """列表用：不含正文。"""
    id: str
    project_id: str
    filename: str
    content_type: str
    size: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReferenceDoc(ReferenceDocSummary):
    """详情/上传返回：含正文。"""
    content_text: str
