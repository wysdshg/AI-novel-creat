"""条件分支节点：按多条件组合判断，决定走 if_else:true / if_else:false 出边。

出边配置：选中本节点后把下游边的 condition 设为 if_else:true 或 if_else:false。
"""
from typing import Any, Optional

from ..base import BaseNode, NodeResult


def _num(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _compare(op: str, actual: Any, expected: Any) -> bool:
    op = (op or "eq").strip().lower()
    if op in ("empty", "not_empty"):
        empty = actual is None or actual == "" or actual == [] or actual == {}
        return empty if op == "empty" else not empty
    if op in ("contains", "not_contains"):
        hit = str(expected) in str(actual or "")
        return hit if op == "contains" else not hit
    if op == "start_with":
        return str(actual or "").startswith(str(expected))
    if op == "end_with":
        return str(actual or "").endswith(str(expected))
    a, b = _num(actual), _num(expected)
    if a is not None and b is not None:
        if op == "eq": return a == b
        if op == "ne": return a != b
        if op == "gt": return a > b
        if op == "ge": return a >= b
        if op == "lt": return a < b
        if op == "le": return a <= b
    # 数值比较失败时回退字符串比较（仅 eq/ne 有意义）
    if op == "eq": return str(actual) == str(expected)
    if op == "ne": return str(actual) != str(expected)
    return False


class IfElseNode(BaseNode):
    node_type = "if-else"
    node_label = "条件分支"
    category = "逻辑控制"
    description = "按条件选择执行路径：result=true 走 if_else:true 出边，否则走 if_else:false 出边。"
    params_schema = [
        {
            "name": "conditions",
            "label": "条件",
            "type": "multifield",
            "required": True,
            "help": "每个条件：{selector: 变量选择器（如 start.word_count）, operator, value}。operator: contains/not_contains/eq/ne/gt/ge/lt/le/empty/not_empty/start_with/end_with",
        },
        {
            "name": "logical",
            "label": "条件间逻辑",
            "type": "select",
            "default": "and",
            "options": ["and", "or"],
        },
    ]
    outputs_desc = {"result": "true / false（决定走哪条出边）"}

    def _run(self, pool, db, inputs: dict) -> NodeResult:
        conds = self.params.get("conditions") or []
        conds = [c for c in conds if isinstance(c, dict)]
        if not conds:
            return NodeResult(status="failed", error="未配置任何条件")
        logical = (self.params.get("logical") or "and").strip().lower()
        results = []
        for c in conds:
            sel = c.get("selector") or c.get("variable_selector")
            op = c.get("operator") or "eq"
            expected = c.get("value")
            actual = pool.resolve_selector(str(sel)) if isinstance(sel, str) else None
            results.append(_compare(op, actual, expected))
        final = all(results) if logical == "and" else any(results)
        return NodeResult(outputs={"result": bool(final)})
