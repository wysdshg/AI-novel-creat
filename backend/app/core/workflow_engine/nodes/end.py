"""结束节点：收集若干变量作为工作流最终输出（对标 Dify End）。"""
from ..base import BaseNode, NodeResult


class EndNode(BaseNode):
    node_type = "end"
    node_label = "结束"
    category = "基础"
    description = "工作流出口：选择若干变量作为最终输出（运行结果的 outputs）。"
    params_schema = [
        {
            "name": "outputs",
            "label": "输出变量",
            "type": "multifield",
            "required": False,
            "help": "每个输出格式：{name: 显示名, selector: 变量选择器（形如 llm_1.text）}",
        },
    ]
    outputs_desc = {"<输出名>": "最终结果（运行详情里展示）"}

    def _run(self, pool, db, inputs: dict) -> NodeResult:
        declared = self.params.get("outputs") or []
        outputs = {}
        for o in declared:
            if not isinstance(o, dict):
                continue
            name = o.get("name")
            sel = o.get("selector")
            if name and sel:
                val = pool.resolve_selector(str(sel))
                if val is not None:
                    outputs[name] = val
        return NodeResult(outputs=outputs)
