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


class ReferenceDocUpdate(BaseModel):
    filename: str = Field(..., min_length=1, max_length=200)


class ReferenceDocSummary(BaseModel):
    """列表用：不含正文。"""
    id: str
    project_id: str
    filename: str
    content_type: str
    size: int
    article_id: Optional[str] = None  # 非空 = 篇章参考文档（按篇维度，AI 生成章后写入）
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReferenceDoc(ReferenceDocSummary):
    """详情/上传返回：含正文。"""
    content_text: str


class ReferenceCatalogItem(BaseModel):
    """按需加载目录项：给 AI 看的「文件清单」（不含正文，含元信息帮助决策）。

    token_est 为启发式估算（零依赖）：中文按项目口径 1 token ≈ 1.5 字符，
    即 round(len(content_text)/1.5)。仅用于 AI 判断「这份文件占多大、要不要加载」，
    后端预算系统仍按字符算，不受影响。
    """
    id: str
    filename: str
    summary: Optional[str] = None        # ORM.summary：要旨，AI 快速判断是否相关
    tags: list[str] = []                  # ORM.tags：检索关键词
    source: str = "upload"                # upload / global / auto
    size: int = 0                         # 字节
    content_chars: int = 0                # 正文字符数（运行时 len(content_text)）
    token_est: int = 0                    # 估算 token 数（content_chars/1.5）
    article_id: Optional[str] = None
    locked: bool = False                  # True=必备上下文（篇章摘要/auto），AI 不可跳过

    model_config = {"from_attributes": True}
