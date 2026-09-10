"""变量池：节点输出存储 + {{#node_id.var#}} 模板引用解析。

对齐 Dify 变量系统：
- 每个节点执行后把 outputs 写入池（key = 节点 id）
- 下游节点用 {{#node_id.var#}} 引用；嵌套取值支持 {{#node_id.var.sub#}}（dict 内层）
- 运行入参统一挂在 start 节点输出上（Dify 语义）；同时支持 inputs.xxx 快捷引用
- 解析不到的引用保留原文，方便用户在画布里发现拼写错误
"""
import json
import re
from typing import Any, Dict, Optional

_SEL_RE = re.compile(r"\{\{#([^#}]+)#\}\}")


def _deep_get(d: Any, keys: list) -> Any:
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        elif isinstance(cur, list) and k.isdigit() and int(k) < len(cur):
            cur = cur[int(k)]
        else:
            return None
    return cur


class VariablePool:
    def __init__(self, inputs: Optional[dict] = None):
        self.inputs: Dict[str, Any] = dict(inputs or {})
        self._outputs: Dict[str, dict] = {}   # node_id -> outputs dict

    # ---- 写入 ----
    def set_output(self, node_id: str, outputs: dict):
        self._outputs[node_id] = outputs or {}

    # ---- 读取 ----
    def get_node(self, node_id: str) -> dict:
        return self._outputs.get(node_id, {})

    def resolve_selector(self, selector: str) -> Any:
        """'node_id.var' 或 'node_id.var.sub'；inputs.xxx 取运行入参。"""
        if not selector or not isinstance(selector, str):
            return None
        if selector.startswith("inputs."):
            return _deep_get(self.inputs, selector[len("inputs."):].split("."))
        parts = selector.split(".")
        if len(parts) < 2:
            return None
        node_id = parts[0]
        if node_id not in self._outputs:
            return None
        return _deep_get(self._outputs[node_id], parts[1:])

    def resolve_value(self, raw: Any) -> Any:
        """变量引用或固定值二选一：形如引用（含 . 或以 inputs. 开头）先尝试解析，
        解析失败或本来就是普通值（UUID/数字/文本）则原样返回。画布字段填固定值也兼容。"""
        if isinstance(raw, str) and ("." in raw or raw.startswith("inputs.")):
            val = self.resolve_selector(raw)
            if val is not None:
                return val
        return raw

    def render(self, text: str) -> str:
        """把 {{#node.var#}} 全部替换成变量值；dict/list 序列化为 JSON。"""
        if not text or "{{#" not in text:
            return text or ""
        def _rep(m: re.Match) -> str:
            val = self.resolve_selector(m.group(1))
            if val is None:
                return m.group(0)
            if isinstance(val, (dict, list)):
                return json.dumps(val, ensure_ascii=False)
            return str(val)
        return _SEL_RE.sub(_rep, text)
