"""工作流 CRUD（全局共享）。nodes/edges 以 JSON 存，符合 Workflow schema 校验。

可扩展点：
- list_active()：只取 is_active=True 的；用于运行时筛选推荐
- duplicate(id)：复制工作流（id 重新生成，name 加 "(副本)"）
- export/import：本轮不实现，留 TODO
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.orm import WorkflowORM
from app.schemas.workflow import (
    Workflow,
    WorkflowCreate,
    WorkflowUpdate,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_schema(o: WorkflowORM) -> Workflow:
    # WorkflowORM 的 nodes/edges 是 list[dict]；用 Pydantic 转换时需 alias for "from"
    # FlowEdge 字段命名为 "from_"（alias "from"），model_validate 兼容 dict 输入。
    return Workflow.model_validate({
        "id": o.id,
        "name": o.name,
        "description": o.description,
        "nodes": o.nodes or [],
        "edges": o.edges or [],
        "tags": o.tags or [],
        "is_active": o.is_active,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
    })


def list_workflows(
    db: Session,
    active_only: bool = False,
    keyword: Optional[str] = None,
) -> list[Workflow]:
    q = db.query(WorkflowORM)
    if active_only:
        q = q.filter(WorkflowORM.is_active.is_(True))
    rows = q.order_by(WorkflowORM.updated_at.desc()).all()
    if keyword:
        k = keyword.lower()
        rows = [
            o for o in rows
            if k in (o.name or "").lower()
            or k in (o.description or "").lower()
            or any(k in str(t).lower() for t in (o.tags or []))
        ]
    return [_to_schema(r) for r in rows]


def create_workflow(db: Session, data: WorkflowCreate) -> Workflow:
    now = _now()
    edges_dump = [e.model_dump(by_alias=True, exclude_none=True) for e in data.edges]
    nodes_dump = [n.model_dump(exclude_none=True) for n in data.nodes]
    o = WorkflowORM(
        id=uuid.uuid4().hex,
        name=data.name,
        description=data.description,
        nodes=nodes_dump,
        edges=edges_dump,
        tags=data.tags or [],
        is_active=data.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def get_workflow(db: Session, wf_id: str) -> Optional[Workflow]:
    o = db.query(WorkflowORM).filter_by(id=wf_id).first()
    return _to_schema(o) if o else None


def update_workflow(
    db: Session, wf_id: str, data: WorkflowUpdate
) -> Optional[Workflow]:
    o = db.query(WorkflowORM).filter_by(id=wf_id).first()
    if o is None:
        return None
    payload = data.model_dump(exclude_unset=True)
    if "nodes" in payload:
        o.nodes = [n if isinstance(n, dict) else n.model_dump(exclude_none=True) for n in payload["nodes"]]
        payload.pop("nodes")
    if "edges" in payload:
        o.edges = [e if isinstance(e, dict) else e.model_dump(by_alias=True, exclude_none=True) for e in payload["edges"]]
        payload.pop("edges")
    for k, v in payload.items():
        setattr(o, k, v)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def delete_workflow(db: Session, wf_id: str) -> bool:
    o = db.query(WorkflowORM).filter_by(id=wf_id).first()
    if o is None:
        return False
    db.delete(o)
    db.commit()
    return True


def duplicate_workflow(db: Session, wf_id: str) -> Optional[Workflow]:
    """复制工作流（id 重生，name 加 "(副本)"）。"""
    o = db.query(WorkflowORM).filter_by(id=wf_id).first()
    if o is None:
        return None
    now = _now()
    copy = WorkflowORM(
        id=uuid.uuid4().hex,
        name=f"{o.name} (副本)",
        description=o.description,
        # 浅拷贝即可，nodes/edges 是不可变 dict 列表的引用；
        # 真要彻底隔离可 deep copy，但此处没必要。
        nodes=o.nodes,
        edges=o.edges,
        tags=list(o.tags or []),
        is_active=o.is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _to_schema(copy)
