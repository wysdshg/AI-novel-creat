"""套路模板组件（需求 11）。"""
from pydantic import BaseModel, Field
from typing import Optional, List


class TemplateMeta(BaseModel):
    id: str
    name: str                                 # 秘境夺宝/宗门大比/…
    description: Optional[str] = None


class OutlineGenerateRequest(BaseModel):
    template_id: str
    participants: List[str] = []              # 参与角色ID
    opponent_faction: Optional[str] = None    # 对立势力
    core_conflict: Optional[str] = None
    background_source: str = Field("manual", description="manual|ai_auto")
    background_text: Optional[str] = None
    config: dict = Field(default_factory=dict)  # conflict_node/mid_turn/ending/est_chapters


class OutlineChapter(BaseModel):
    chapter_no: int
    core_content: str
    characters: List[str] = []
    foreshadow_slots: List[str] = []


class Outline(BaseModel):
    id: str
    project_id: str
    template_id: str
    chapters: List[OutlineChapter] = []
    status: str = "draft"
