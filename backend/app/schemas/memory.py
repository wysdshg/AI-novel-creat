"""记忆压缩（需求 8）。"""
from pydantic import BaseModel, Field
from typing import Optional, List


class ChapterSummary(BaseModel):
    chapter_no: int
    core_event: Optional[str] = None          # 章节核心事件
    character_states: List[dict] = []         # 出场人物状态
    new_foreshadows: List[str] = []           # 新增伏笔
    emotion_shift: Optional[str] = None       # 人物情绪变化
    mainline_progress: Optional[str] = None   # 主线进度


class MajorEvent(BaseModel):
    chapter_no: int
    event: str                                # 极简大事记


class MemorySummary(BaseModel):
    recent: List[ChapterSummary] = []         # 最近 3 章详细
    events: List[MajorEvent] = []             # 更早极简大事记
