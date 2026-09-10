"""开始节点：工作流入口，校验并暴露输入变量（对标 Dify Start）。"""
from typing import Any, Dict, List

from ..base import BaseNode, NodeResult


class StartNode(BaseNode):
    node_type = "start"
    node_label = "开始"
    category = "基础"
    description = "工作流入口：定义输入变量（名称/类型/必填/默认值），运行时在此填写。"
    params_schema = [
        {
            "name": "variables",
            "label": "输入变量",
            "type": "multifield",
            "required": True,
            "help": "每个变量格式：{name: 变量名, label: 显示名, type: string|number|select, required: true/false, default: 默认值, options: [下拉选项]}",
        },
    ]
    outputs_desc = {"<变量名>": "运行入参的值（供下游 {{#start.变量名#}} 引用）"}

    def _run(self, pool, db, inputs: dict) -> NodeResult:
        declared: List[Dict[str, Any]] = self.params.get("variables") or []
        outputs: Dict[str, Any] = {}
        missing = []
        for v in declared:
            if not isinstance(v, dict):
                continue
            name = v.get("name")
            if not name:
                continue
            if name in pool.inputs and pool.inputs[name] is not None:
                outputs[name] = pool.inputs[name]
            elif v.get("default") is not None:
                outputs[name] = v["default"]
            elif v.get("required"):
                missing.append(v.get("label") or name)
        if missing:
            return NodeResult(
                status="failed",
                error=f"缺少必填输入: {', '.join(missing)}",
                outputs=outputs,
            )
        return NodeResult(outputs=outputs)
