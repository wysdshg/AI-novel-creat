"""剧情走向推荐（需求 5）。"""
from pydantic import BaseModel, Field
from typing import Optional, List


class Direction(BaseModel):
    id: str
    chapter_id: str
    core_conflict: str                        # 核心冲突
    applicable_foreshadows: List[str] = []    # 适用伏笔
    character_change: Optional[str] = None    # 人物变化
    style_bias: Optional[str] = None          # 风格偏向
    confidence: float = Field(0.0, ge=0, le=1)
