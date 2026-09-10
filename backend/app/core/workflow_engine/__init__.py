"""工作流执行引擎（对标 Dify Workflow Engine）。

对外唯一入口：run_workflow(wf_id, inputs, event_cb)
- 独立 DB session（gen_db 模式，见项目记忆⑥：绝不碰请求级 session）
- 图引擎执行 → 落 WorkflowRun / WorkflowNodeRun 记录
- event_cb 实时回调 node_start / node_end，供 SSE 端点转发

执行流程：
1. 读 WorkflowORM（nodes/edges）
2. GraphEngine.validate()（单 start/end、无环）
3. 依赖驱动执行（入度法 + 条件边路由）
4. 写运行记录（finally 保证失败也落库）
"""
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from app.core import database as _db
from app.models.orm import WorkflowNodeRunORM, WorkflowORM, WorkflowRunORM

from .engine import GraphEngine, WorkflowError
from .nodes import make_node


def _now() -> datetime:
    return datetime.now(timezone.utc)


def node_meta_list() -> list:
    """节点类型目录（GET /workflows/meta/node-types）。"""
    from .nodes import NODE_CLASSES
    return [cls.meta() for cls in NODE_CLASSES]


def run_workflow(
    workflow_id: str,
    inputs: Optional[dict] = None,
    event_cb: Optional[Callable[[str, dict], None]] = None,
) -> dict:
    """执行工作流，返回 {"run": {...}, "node_runs": [...]}。

    event_cb(event_type, payload)：node_start / node_end（同步回调）。
    事件 payload 与落库内容一致，SSE 端点经线程+队列实时转发。
    """
    gen_db = _db.SessionLocal()
    run_id = uuid.uuid4().hex
    run_orm = None
    t0 = None
    try:
        wf = gen_db.query(WorkflowORM).filter_by(id=workflow_id).first()
        if wf is None:
            raise WorkflowError("工作流不存在")

        run_orm = WorkflowRunORM(
            id=run_id,
            workflow_id=workflow_id,
            status="running",
            inputs=inputs or {},
            outputs={},
            started_at=_now(),
        )
        gen_db.add(run_orm)
        gen_db.commit()
        gen_db.refresh(run_orm)

        engine = GraphEngine(wf.nodes or [], wf.edges or [])
        t0 = time.time()

        def _cb(evt: str, payload: dict):
            if event_cb:
                event_cb(evt, payload)

        outcome = engine.run(inputs or {}, node_factory=make_node, db=gen_db, event_cb=_cb)
        duration_ms = int((time.time() - t0) * 1000)

        # 最终结果 = end 节点 outputs
        end_id = next(n["id"] for n in (wf.nodes or []) if n.get("type") == "end")
        end_result = outcome["results"].get(end_id)
        run_outputs = end_result.outputs if end_result else {}
        run_status = "success"
        run_error = None
        for nid, r in outcome["results"].items():
            if r.status == "failed":
                run_status = "failed"
                run_error = r.error
                break

        # 落节点轨迹（含 skipped 补记）
        node_runs = []
        executed = outcome["results"]
        for n in (wf.nodes or []):
            nid = n.get("id")
            res = executed.get(nid)
            node_runs.append({
                "id": uuid.uuid4().hex,
                "run_id": run_id,
                "workflow_id": workflow_id,
                "node_id": nid,
                "node_type": n.get("type") or "generic",
                "label": n.get("label") or "",
                "status": res.status if res else "skipped",
                "inputs": res.inputs if res else {},
                "outputs": res.outputs if res else {},
                "error": res.error if res else None,
                "duration_ms": res.duration_ms if res else None,
                "created_at": _now(),
            })
        gen_db.add_all([WorkflowNodeRunORM(**nr) for nr in node_runs])

        # 更新 run 记录
        run_orm.status = run_status
        run_orm.outputs = run_outputs
        run_orm.error = run_error
        run_orm.finished_at = _now()
        run_orm.duration_ms = duration_ms
        gen_db.commit()

        return {
            "run": {
                "id": run_id,
                "workflow_id": workflow_id,
                "status": run_status,
                "inputs": inputs or {},
                "outputs": run_outputs,
                "error": run_error,
                "duration_ms": duration_ms,
                "started_at": run_orm.started_at,
                "finished_at": run_orm.finished_at,
            },
            "node_runs": node_runs,
        }
    except Exception as e:  # noqa: BLE001
        # 失败也要留痕（含配置错误/引擎异常）
        if run_orm is not None:
            run_orm.status = "failed"
            run_orm.error = str(e)[:2000]
            run_orm.finished_at = _now()
            run_orm.duration_ms = int((time.time() - t0) * 1000) if t0 else None
            try:
                gen_db.commit()
            except Exception:  # noqa: BLE001
                gen_db.rollback()
        raise
    finally:
        gen_db.close()
