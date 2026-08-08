"""ORM 数据模型（对应 API接口规范.md 各实体）。

声明基类 Base 由 core.database 统一提供，确保建表元数据唯一。
分作品隔离（§1）：所有业务实体含 project_id 字段。
"""
from datetime import datetime
from sqlalchemy import (
    String, Integer, Text, Boolean, DateTime, Float, ForeignKey, JSON
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProjectORM(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    genre: Mapped[str | None] = mapped_column(String(40), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    db_backend: Mapped[str] = mapped_column(String(20), default="sqlite")
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CharacterORM(Base):
    __tablename__ = "characters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(80))
    role_type: Mapped[str | None] = mapped_column(String(20), nullable=True)   # 主角/配角/反派
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)      # 男/女/其他
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)       # 性格
    background: Mapped[str | None] = mapped_column(Text, nullable=True)        # 背景
    talent: Mapped[str | None] = mapped_column(Text, nullable=True)            # 天赋
    current_level: Mapped[str | None] = mapped_column(String(40), nullable=True)  # 当前等级
    skills: Mapped[list] = mapped_column(JSON, default=list)                   # 技能
    relationship_network: Mapped[list] = mapped_column(JSON, default=list)     # 关系网
    # ---- 关系网可视化布局坐标（SVG 画布坐标系，可拖拽持久化）----
    network_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    network_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    brief: Mapped[str | None] = mapped_column(Text, nullable=True)             # 简介
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SkillORM(Base):
    __tablename__ = "skills"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(80))
    level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitation: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    side_effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    unlock_condition: Mapped[str | None] = mapped_column(Text, nullable=True)


class RelationORM(Base):
    __tablename__ = "relations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    subject_id: Mapped[str] = mapped_column(String(36))
    object_id: Mapped[str] = mapped_column(String(36))
    relation_type: Mapped[str] = mapped_column(String(20))
    strength: Mapped[int] = mapped_column(Integer, default=50)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class FactionORM(Base):
    __tablename__ = "factions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    leader_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    members: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LocationORM(Base):
    __tablename__ = "locations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(80))
    location_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 城市/秘境/洞府/门派/其他
    region: Mapped[str | None] = mapped_column(String(80), nullable=True)         # 所属区域
    description: Mapped[str | None] = mapped_column(Text, nullable=True)          # 描述
    notable_features: Mapped[list] = mapped_column(JSON, default=list)            # 特色/地标
    related_ids: Mapped[list] = mapped_column(JSON, default=list)                 # 关联角色/势力
    # ---- 空间几何建模（统一世界坐标系 x/y + 位面 plane + 高度 height）----
    plane: Mapped[str | None] = mapped_column(String(40), nullable=True)          # 位面/地图标签：凡间/仙界/地狱/秘境/自定义
    center_x: Mapped[float | None] = mapped_column(Float, nullable=True)          # 世界坐标系横坐标
    center_y: Mapped[float | None] = mapped_column(Float, nullable=True)          # 世界坐标系纵坐标
    shape: Mapped[str | None] = mapped_column(String(20), nullable=True)          # point/circle/rect/sector/polygon
    radius: Mapped[float | None] = mapped_column(Float, nullable=True)            # 圆/扇形半径，或矩形半宽
    radius_y: Mapped[float | None] = mapped_column(Float, nullable=True)          # 矩形半高
    angle: Mapped[float | None] = mapped_column(Float, nullable=True)             # 扇形中心朝向（度）
    angle_span: Mapped[float | None] = mapped_column(Float, nullable=True)        # 扇形张角（度）
    height: Mapped[float | None] = mapped_column(Float, nullable=True)            # 高度/海拔（第三维）
    polygon: Mapped[list | None] = mapped_column(JSON, nullable=True)             # 不规则多边形顶点 [[x,y],...]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class ForeshadowORM(Base):
    __tablename__ = "foreshadows"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    description: Mapped[str] = mapped_column(Text)
    buried_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scene: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    activated_chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    related_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending")


class ChapterORM(Base):
    __tablename__ = "chapters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    chapter_no: Mapped[int] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DiscussionMessageORM(Base):
    __tablename__ = "discussion_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(10))            # user / assistant
    content: Mapped[str] = mapped_column(Text)
    # ---- 商讨缓存持久化增强字段 ----
    thinking: Mapped[str | None] = mapped_column(Text, nullable=True)        # 思考过程（开启思考时）
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)           # {enable_thinking, model} 等
    archived_chapter_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # 非空=已归档到该章节
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ModelConfigORM(Base):
    __tablename__ = "model_configs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    vendor: Mapped[str] = mapped_column(String(20))
    api_base: Mapped[str] = mapped_column(String(255))
    api_key: Mapped[str] = mapped_column(String(255), default="")
    model_name: Mapped[str] = mapped_column(String(80))
    context_window: Mapped[int] = mapped_column(Integer, default=32768)
    temperature: Mapped[float] = mapped_column(Float, default=0.4)
    top_p: Mapped[float] = mapped_column(Float, default=0.9)
    max_tokens: Mapped[int] = mapped_column(Integer, default=6000)
    role: Mapped[str] = mapped_column(String(20), default="primary")
    is_backup: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_thinking: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DirectionORM(Base):
    __tablename__ = "directions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    chapter_id: Mapped[str] = mapped_column(String(36))
    core_conflict: Mapped[str] = mapped_column(Text)
    applicable_foreshadows: Mapped[list] = mapped_column(JSON, default=list)
    character_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_bias: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)


class OutlineORM(Base):
    __tablename__ = "outlines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    template_id: Mapped[str] = mapped_column(String(36))
    chapters: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")


class ReferenceDocORM(Base):
    """每本小说的参考文档（§用户需求：手动上传，供 AI 生成时参考读取）。

    以纯文本形式存储文件内容，便于直接拼入生成 Prompt。
    支持 .txt/.md/.json/.csv/.log 等文本类文件；PDF/Word 等二进制解析后续扩展。
    """
    __tablename__ = "reference_docs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(60), default="text/plain")
    size: Mapped[int] = mapped_column(Integer, default=0)            # 字节数
    content_text: Mapped[str] = mapped_column(Text, default="")      # 文本正文
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
