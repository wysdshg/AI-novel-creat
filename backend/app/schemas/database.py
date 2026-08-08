"""资料库实体：角色/技能/关系/势力/伏笔（需求 1、4、9、10）。"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ---------- 角色（11 字段，与前端表单一致） ----------
class CharacterBase(BaseModel):
    name: str = Field(..., max_length=80, description="姓名")
    role_type: Optional[str] = Field(None, description="小说中地位：主角/配角/反派")
    age: Optional[int] = Field(None, ge=0, le=999, description="年龄")
    gender: Optional[str] = Field(None, description="性别：男/女/其他")
    personality: Optional[str] = None            # 性格
    background: Optional[str] = None             # 背景
    talent: Optional[str] = None                 # 天赋
    current_level: Optional[str] = Field(None, description="当前等级/境界")
    skills: List[str] = []                       # 技能（自由文本条目）
    relationship_network: List[str] = []         # 关系网（自由文本条目）
    brief: Optional[str] = None                  # 简介
    network_x: Optional[float] = None            # 关系网布局 X（SVG 画布坐标）
    network_y: Optional[float] = None            # 关系网布局 Y（SVG 画布坐标）


class CharacterCreate(CharacterBase):
    pass


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    role_type: Optional[str] = None
    age: Optional[int] = Field(None, ge=0, le=999)
    gender: Optional[str] = None
    personality: Optional[str] = None
    background: Optional[str] = None
    talent: Optional[str] = None
    current_level: Optional[str] = None
    skills: Optional[List[str]] = None
    relationship_network: Optional[List[str]] = None
    brief: Optional[str] = None
    network_x: Optional[float] = None
    network_y: Optional[float] = None


class Character(CharacterBase):
    id: str
    created_at: datetime
    updated_at: datetime


# ---------- 技能 ----------
class SkillBase(BaseModel):
    name: str
    level: Optional[str] = None
    effect: Optional[str] = None              # 效果
    limitation: Optional[str] = None          # 使用限制
    owner_id: Optional[str] = None            # 持有者角色ID
    side_effect: Optional[str] = None         # 副作用
    unlock_condition: Optional[str] = None    # 解锁条件


class SkillCreate(SkillBase):
    pass


class SkillUpdate(BaseModel):
    name: Optional[str] = None
    level: Optional[str] = None
    effect: Optional[str] = None
    limitation: Optional[str] = None
    owner_id: Optional[str] = None
    side_effect: Optional[str] = None
    unlock_condition: Optional[str] = None


class Skill(SkillBase):
    id: str


# ---------- 关系 ----------
class RelationBase(BaseModel):
    subject_id: str                           # 主体A
    object_id: str                            # 客体B
    relation_type: str = Field(..., description="友好/敌对/亲人/师徒/上下级/暧昧…")
    strength: int = Field(50, ge=0, le=100)   # 关系强度
    note: Optional[str] = None                # 特殊恩怨备注


class RelationCreate(RelationBase):
    pass


class RelationUpdate(BaseModel):
    relation_type: Optional[str] = None
    strength: Optional[int] = Field(None, ge=0, le=100)
    note: Optional[str] = None


class Relation(RelationBase):
    id: str


# ---------- 势力 ----------
class FactionBase(BaseModel):
    name: str
    description: Optional[str] = None
    leader_id: Optional[str] = None
    members: List[str] = []                   # 角色ID
    status: Optional[str] = None


class FactionCreate(FactionBase):
    pass


class FactionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    leader_id: Optional[str] = None
    members: Optional[List[str]] = None
    status: Optional[str] = None


class Faction(FactionBase):
    id: str


# ---------- 地点 ----------
class LocationBase(BaseModel):
    name: str
    location_type: Optional[str] = None        # 城市/秘境/洞府/门派/其他
    region: Optional[str] = None               # 所属区域
    description: Optional[str] = None          # 描述
    notable_features: List[str] = []           # 特色/地标
    related_ids: List[str] = []                # 关联角色/势力
    # ---- 空间几何建模 ----
    plane: Optional[str] = None                # 位面/地图标签（凡间/仙界/地狱/秘境/自定义）
    center_x: Optional[float] = None           # 世界坐标系横坐标
    center_y: Optional[float] = None           # 世界坐标系纵坐标
    shape: Optional[str] = None                # point/circle/rect/sector/polygon
    radius: Optional[float] = None             # 圆/扇形半径，或矩形半宽
    radius_y: Optional[float] = None           # 矩形半高
    angle: Optional[float] = None              # 扇形中心朝向（度）
    angle_span: Optional[float] = None         # 扇形张角（度）
    height: Optional[float] = None             # 高度/海拔（第三维）
    polygon: Optional[List[List[float]]] = None  # 不规则多边形顶点 [[x,y],...]


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    location_type: Optional[str] = None
    region: Optional[str] = None
    description: Optional[str] = None
    notable_features: Optional[List[str]] = None
    related_ids: Optional[List[str]] = None
    plane: Optional[str] = None
    center_x: Optional[float] = None
    center_y: Optional[float] = None
    shape: Optional[str] = None
    radius: Optional[float] = None
    radius_y: Optional[float] = None
    angle: Optional[float] = None
    angle_span: Optional[float] = None
    height: Optional[float] = None
    polygon: Optional[List[List[float]]] = None


class Location(LocationBase):
    id: str


# ---------- 伏笔（需求 9，详见 foreshadow 路由） ----------
class ForeshadowBase(BaseModel):
    description: str
    buried_chapter: Optional[int] = None      # 埋下章节号
    scene: Optional[str] = None               # 适用场景
    trigger_condition: Optional[str] = None   # 触发条件
    enabled: bool = True
    activated_chapter: Optional[int] = None   # 启用章节号
    related_ids: List[str] = []               # 关联角色/势力
    status: str = Field("pending", description="pending|active|done")


class ForeshadowCreate(ForeshadowBase):
    pass


class ForeshadowUpdate(BaseModel):
    description: Optional[str] = None
    buried_chapter: Optional[int] = None
    scene: Optional[str] = None
    trigger_condition: Optional[str] = None
    enabled: Optional[bool] = None
    activated_chapter: Optional[int] = None
    related_ids: Optional[List[str]] = None
    status: Optional[str] = None


class Foreshadow(ForeshadowBase):
    id: str


# ---------- 设定校验（需求 4） ----------
class ValidateRequest(BaseModel):
    text: Optional[str] = Field(None, description="待校验正文")
    character_ids: List[str] = []


class ValidateIssue(BaseModel):
    type: str = Field(..., description="性格崩坏/技能乱用/关系矛盾")
    level: str = Field(..., description="轻微/严重")
    offset: int = 0
    length: int = 0
    detail: Optional[str] = None


class ValidateResult(BaseModel):
    constraint_list: List[str] = []
    issues: List[ValidateIssue] = []


# ---------- 自然语言指令（需求 10） ----------
class CommandRequest(BaseModel):
    text: str
    dry_run: bool = False


class CommandResult(BaseModel):
    intent: Optional[str] = None
    changes: List[dict] = []
    clarification: Optional[str] = None       # 无法解析时的澄清问句
