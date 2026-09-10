"""工作流 API（全局共享）。

端点清单见 docs/接口与组件文档.md §5 工作流。
- CRUD：列表 / 详情 / 新建 / 修改 / 删除 / 复制
- 运行：POST /workflows/{wf_id}/runs（SSE 流式），历史 GET /{wf_id}/runs，详情 GET /runs/{run_id}
- 节点目录：GET /workflows/meta/node-types（前端节点面板渲染用）
"""
import logging
import queue
import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok, sse_event
from app.models.orm import WorkflowNodeRunORM, WorkflowRunORM
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate, WorkflowRunRequest
from app.services import workflow_crud as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["工作流（全局）"])


@router.get("/meta/node-types", summary="节点类型目录（前端节点面板用）")
def node_types_meta():
    from app.core.workflow_engine import node_meta_list
    return ok({"nodes": node_meta_list()})


@router.get("", summary="列出工作流")
def list_workflows(
    active_only: bool = Query(False, description="只取 is_active=True"),
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    return ok([w.model_dump(mode="json", by_alias=True) for w in svc.list_workflows(
        db, active_only=active_only, keyword=keyword
    )])


@router.post("", summary="新建工作流")
def create_workflow(body: WorkflowCreate, db: Session = Depends(get_session)):
    w = svc.create_workflow(db, body)
    return ok(w.model_dump(mode="json", by_alias=True))


@router.get("/{wf_id}", summary="工作流详情")
def get_workflow(wf_id: str, db: Session = Depends(get_session)):
    w = svc.get_workflow(db, wf_id)
    if w is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return ok(w.model_dump(mode="json", by_alias=True))


@router.put("/{wf_id}", summary="修改工作流")
def update_workflow(
    wf_id: str, body: WorkflowUpdate, db: Session = Depends(get_session)
):
    w = svc.update_workflow(db, wf_id, body)
    if w is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return ok(w.model_dump(mode="json", by_alias=True))


@router.delete("/{wf_id}", summary="删除工作流")
def delete_workflow(wf_id: str, db: Session = Depends(get_session)):
    if not svc.delete_workflow(db, wf_id):
        raise HTTPException(status_code=404, detail="工作流不存在")
    return ok({"deleted": wf_id})


@router.post("/{wf_id}/duplicate", summary="复制工作流（id 重新生成，name 加'(副本)'）")
def duplicate_workflow(wf_id: str, db: Session = Depends(get_session)):
    w = svc.duplicate_workflow(db, wf_id)
    if w is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return ok(w.model_dump(mode="json", by_alias=True))


# ============================================================================
# 运行（SSE 流式执行）
# ============================================================================
@router.post("/{wf_id}/runs", summary="运行工作流（SSE：node_start/node_end/run_end）")
def run_workflow(wf_id: str, body: WorkflowRunRequest, db: Session = Depends(get_session)):
    from app.core.workflow_engine import run_workflow as _run
    from app.core.workflow_engine.engine import GraphEngine, WorkflowError

    wf = svc.get_workflow(db, wf_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    # 配置错误（单 start/end、环等）提前暴露为非流式 400，避免用户白等
    try:
        nodes = [n.model_dump(by_alias=True) for n in (wf.nodes or [])]
        edges = [e.model_dump(by_alias=True) for e in (wf.edges or [])]
        GraphEngine(nodes, edges).validate()
    except WorkflowError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def event_stream():
        q: "queue.Queue" = queue.Queue()
        holder: dict = {}

        def _cb(evt: str, payload: dict):
            q.put(("event", evt, payload))

        def _worker():
            try:
                holder["result"] = _run(wf_id, body.inputs or {}, event_cb=_cb)
            except Exception as e:  # noqa: BLE001
                # 后台线程的异常无法自然冒泡到请求，只能捕获后经 SSE 的 error/run_end 事件回传。
                # 这里必须 log.exception：SSE 只带 500 字截断的消息，堆栈只有日志里有（Phase 3.5）
                logger.exception(f"[workflow] 工作流执行线程异常 wf_id={str(wf_id)[:8]}")
                holder["error"] = e
            finally:
                q.put(("done", None, None))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        while True:
            kind, evt, payload = q.get()
            if kind == "done":
                break
            yield sse_event(evt, payload)
        if holder.get("error"):
            yield sse_event("error", {"message": str(holder["error"])})
            yield sse_event("run_end", {"run_id": wf_id, "status": "failed",
                                   "error": str(holder["error"])[:500]})
        else:
            res = holder.get("result") or {}
            run = res.get("run") or {}
            yield sse_event("run_end", {
                "run_id": run.get("id", wf_id),
                "status": run.get("status", "success"),
                "outputs": run.get("outputs", {}),
                "error": run.get("error"),
                "duration_ms": run.get("duration_ms"),
            })

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{wf_id}/runs", summary="工作流运行历史（最近 50 条）")
def list_runs(wf_id: str, db: Session = Depends(get_session)):
    rows = (
        db.query(WorkflowRunORM)
        .filter_by(workflow_id=wf_id)
        .order_by(WorkflowRunORM.started_at.desc())
        .limit(50)
        .all()
    )
    return ok([{
        "id": r.id,
        "workflow_id": r.workflow_id,
        "status": r.status,
        "inputs": r.inputs,
        "outputs": r.outputs,
        "error": r.error,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
        "duration_ms": r.duration_ms,
    } for r in rows])


@router.get("/runs/{run_id}", summary="运行详情（含节点执行轨迹）")
def get_run(run_id: str, db: Session = Depends(get_session)):
    run = db.query(WorkflowRunORM).filter_by(id=run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    nodes = (
        db.query(WorkflowNodeRunORM)
        .filter_by(run_id=run_id)
        .order_by(WorkflowNodeRunORM.created_at.asc())
        .all()
    )
    return ok({
        "run": {
            "id": run.id,
            "workflow_id": run.workflow_id,
            "status": run.status,
            "inputs": run.inputs,
            "outputs": run.outputs,
            "error": run.error,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "duration_ms": run.duration_ms,
        },
        "node_runs": [{
            "id": n.id,
            "node_id": n.node_id,
            "node_type": n.node_type,
            "label": n.label,
            "status": n.status,
            "inputs": n.inputs,
            "outputs": n.outputs,
            "error": n.error,
            "duration_ms": n.duration_ms,
        } for n in nodes],
    })
