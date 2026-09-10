"""模板转换节点：把 {{#node.var#}} 引用替换成变量值生成新文本（对标 Dify Template）。"""
from ..base import BaseNode, NodeResult


class TemplateNode(BaseNode):
    node_type = "template"
    node_label = "模板转换"
    category = "数据处理"
    description = "把模板中的 {{#node.var#}} 替换为变量值，生成新文本（拼提示词、拼段落）。"
    params_schema = [
        {
            "name": "template",
            "label": "模板",
            "type": "textarea",
            "required": True,
            "help": "支持 {{#node_id.var#}} 引用；dict/list 值自动转 JSON",
        },
    ]
    outputs_desc = {"output": "渲染后的文本"}

    def _run(self, pool, db, inputs: dict) -> NodeResult:
        tpl = self.params.get("template") or ""
        return NodeResult(outputs={"output": pool.render(tpl)})
