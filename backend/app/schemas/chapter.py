"""章节生成与剧情商讨（需求 2、3、6）。"""
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class GenerateRequest(BaseModel):
    chapter_no: int = Field(..., ge=1)
    prompt_hint: Optional[str] = None
    from_discussion: bool = True
    trigger_foreshadow_ids: List[str] = []
    word_range: dict = Field(default_factory=lambda: {"min": 3000, "max": 5000})
    temperature: float = Field(0.4, ge=0, le=1)
    enable_thinking: Optional[bool] = None


class ChapterBase(BaseModel):
    chapter_no: int
    title: Optional[str] = None
    content: str = ""
    note: Optional[str] = None                # 商讨归档备注
    word_count: int = 0


class ChapterCreate(ChapterBase):
    pass


class ChapterUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    note: Optional[str] = None


class Chapter(ChapterBase):
    id: str
    created_at: datetime
    updated_at: datetime


# ---------- 剧情商讨消息（需求 6） ----------
class DiscussionMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class DiscussionMessageCreate(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str


class DiscussionChatRequest(BaseModel):
    """剧情商讨：前端传完整对话历史，后端用默认模型流式回复。"""
    messages: List[dict] = Field(default_factory=list)  # [{role:'user'|'assistant', content}]
    enable_thinking: Optional[bool] = None
    temperature: Optional[float] = None
