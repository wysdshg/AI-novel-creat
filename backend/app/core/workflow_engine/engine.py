"""图引擎（对标 Dify Graph）：DAG 校验 + 依赖驱动执行 + 条件边路由。

执行模型（入度法）：
- 每个节点入度 = 入边数；start 入度必须为 0
- 节点执行完毕后，按每条出边的 condition 判断「是否成立」：
    - always      → 无条件成立
    - success     → 上游执行成功才成立
    - failure     → 上游执行失败才成立
    - if_else:true / if_else:false → 上游 if-else 节点的 result 匹配才成立
- 成立的边把目标节点入度 -1，归零则入队执行
- 汇聚节点（多前驱）天然等所有成立的前驱执行完才触发；
  分支被跳过的节点永远不入队（前端展示为 skipped）
"""
import time
from collections import defaultdict, deque
from typing import Callable, Dict, List, Optional

from .base import NodeResult
from .pool import VariablePool


class WorkflowError(Exception):
    """工作流配置/执行错误（对前端友好展示）。"""


# 条件边取值约定（edge.condition）
COND_ALWAYS = "always"
COND_SUCCESS = "success"          # 兼容 onSuccess
COND_FAILURE = "failure"          # 兼容 onFailure
COND_IF_TRUE = "if_else:true"
COND_IF_FALSE = "if_else:false"


class GraphEngine:
    def __init__(self, nodes: List[dict], edges: List[dict]):
        self.nodes = nodes
        self.edges = edges
        self.by_id: Dict[str, dict] = {n.get("id"): n for n in nodes}
        self.out_edges: Dict[str, list] = defaultdict(list)
        self.in_edges: Dict[str, list] = defaultdict(list)
        for e in edges:
            self.out_edges[e["from"]].append(e)
            self.in_edges[e["to"]].append(e)

    # ------------------------------------------------------------------
    def validate(self) -> None:
        """配置合法性：节点唯一 / 边端点存在 / 单 start / 单 end / 无环。"""
        if not self.by_id:
            raise WorkflowError("工作流没有任何节点")

        ids = set(self.by_id)
        if len(ids) != len(self.nodes):
            raise WorkflowError("节点 id 必须唯一")

        for e in self.edges:
            if e["from"] not in ids or e["to"] not in ids:
                raise WorkflowError(f"边 {e['from']} → {e['to']} 端点不存在")

        starts = [n for n in self.nodes if n.get("type") == "start"]
        ends = [n for n in self.nodes if n.get("type") == "end"]
        if len(starts) != 1:
            raise WorkflowError("工作流必须有且只有一个「开始」节点")
        if len(ends) != 1:
            raise WorkflowError("工作流必须有且只有一个「结束」节点")

        start_id = starts[0]["id"]
        if self.in_edges.get(start_id):
            raise WorkflowError("「开始」节点不允许有入边")

        # Kahn 拓扑：有环 → 拒绝运行（入度法会死锁）
        # end 节点虚拟入度 1：任意一条入边成立即触发（汇聚多分支的简化语义，
        # 与 Dify 一致——End 不是聚合器，聚合留给 Variable Aggregator 二期实现）。
        indeg = {}
        for nid in ids:
            if self.by_id[nid].get("type") == "end" and self.in_edges.get(nid):
                indeg[nid] = 1
            else:
                indeg[nid] = len(self.in_edges[nid])
        q = deque(nid for nid, d in indeg.items() if d == 0)
        visited = 0
        while q:
            cur = q.popleft()
            visited += 1
            for e in self.out_edges[cur]:
                indeg[e["to"]] -= 1
                if indeg[e["to"]] == 0:
                    q.append(e["to"])
        if visited < len(ids):
            raise WorkflowError("工作流存在循环依赖，无法执行（仅支持有向无环图）")

    # ------------------------------------------------------------------
    def run(
        self,
        inputs: dict,
        node_factory: Callable[[dict], object],
        db=None,
        event_cb: Optional[Callable[[str, dict], None]] = None,
    ) -> dict:
        """执行工作流。

        返回 {"pool": VariablePool, "results": {node_id: NodeResult}}。
        event_cb(event_type, payload)：node_start / node_end。
        """
        self.validate()
        pool = VariablePool(inputs)
        results: Dict[str, NodeResult] = {}
        start_id = next(n["id"] for n in self.nodes if n.get("type") == "start")

        indeg = {}
        for nid in self.by_id:
            if self.by_id[nid].get("type") == "end" and self.in_edges.get(nid):
                indeg[nid] = 1
            else:
                indeg[nid] = len(self.in_edges[nid])
        queue = deque([start_id])

        while queue:
            nid = queue.popleft()
            if nid in results:
                continue
            raw = self.by_id[nid]
            node = node_factory(raw)
            t0 = time.time()
            if event_cb:
                event_cb("node_start", {"node_id": nid, "label": node.label, "node_type": node.node_type})
            result = node.run(pool, db)
            result.duration_ms = int((time.time() - t0) * 1000)
            results[nid] = result
            pool.set_output(nid, result.outputs)
            if event_cb:
                event_cb("node_end", {
                    "node_id": nid,
                    "label": node.label,
                    "node_type": node.node_type,
                    "status": result.status,
                    "outputs": result.outputs,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                })

            for e in self.out_edges[nid]:
                if self._edge_matches(nid, result, e):
                    indeg[e["to"]] -= 1
                    if indeg[e["to"]] <= 0 and e["to"] not in results:
                        queue.append(e["to"])

        return {"pool": pool, "results": results}

    # ------------------------------------------------------------------
    def _edge_matches(self, from_id: str, result: NodeResult, edge: dict) -> bool:
        cond = (edge.get("condition") or COND_ALWAYS).strip().lower()
        if cond in ("", COND_ALWAYS):
            return True
        if cond in (COND_SUCCESS, "onsuccess"):
            return result.status == "success"
        if cond in (COND_FAILURE, "onfailure"):
            return result.status == "failed"
        if cond in (COND_IF_TRUE, "if_else:true"):
            return bool(result.outputs.get("result")) is True
        if cond in (COND_IF_FALSE, "if_else:false"):
            return bool(result.outputs.get("result")) is False
        # 未知条件：按 always 处理（宽容，不阻断流程）
        return True
