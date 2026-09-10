"""工作流 Schema（全局共享的创作/剧情流程模板）。

nodes / edges 均为 JSON：DAG（节点 + 条件边）描述，
前端可后续接 vue-flow 等可视化编辑；本轮只做 CRUD 与基本合法性校验。

为可扩展性预留：
- tags：自由标签，便于检索 / 归类
- is_active：是否启用（关闭后仍保留但不被默认推荐）
- 起 version 字段：以后做版本化 / 派生
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, model_validator


# 节点/边的最小结构约束（容许扩展字段，过严会限制前端）
class FlowNode(BaseModel):
    id: str = Field(..., min_length=1, max_length=60)
    type: str = Field("generic", description="节点类型：start / step / branch / ai / end / generic …")
    label: str = Field("", description="显示名")
    params: Dict[str, Any] = Field(default_factory=dict, description="节点参数（自由扩展）")
    position: Optional[Dict[str, float]] = Field(None, description="画布坐标 {x, y}")


class FlowEdge(BaseModel):
    """条件边：condition ∈ {always, onSuccess, onFailure}，自定义字符串也允许。"""
    id: Optional[str] = None
    from_: str = Field(..., alias="from", min_length=1)
    to: str = Field(..., min_length=1)
    condition: str = Field("always")


class WorkflowBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    nodes: List[FlowNode] = Field(default_factory=list)
    edges: List[FlowEdge] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    is_active: bool = True

    @model_validator(mode="after")
    def _validate_dag(self) -> "WorkflowBase":
        """节点 id 唯一；边的端点必须存在。"""
        ids = {n.id for n in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("节点 id 必须唯一")
        for e in self.edges:
            if e.from_ not in ids or e.to not in ids:
                raise ValueError(f"边 {e.from_}→{e.to} 端点不存在于 nodes")
        return self


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = None
    nodes: Optional[List[FlowNode]] = None
    edges: Optional[List[FlowEdge]] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class Workflow(WorkflowBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunRequest(BaseModel):
    """执行工作流：inputs 为 start 节点声明的输入变量值。"""
    inputs: Dict[str, Any] = Field(default_factory=dict)
