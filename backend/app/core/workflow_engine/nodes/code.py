"""代码执行节点：受限 Python 片段做数据变换（对标 Dify Code）。

安全：白名单 builtins + 禁用 __/import/eval/exec/open，杜绝危险调用。
用途：字数统计、文本清洗、把数组拼成提示词等。
"""
import builtins
import logging

from ..base import BaseNode, NodeResult

logger = logging.getLogger(__name__)

_SAFE_BUILTIN_NAMES = {
    "len", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
    "range", "enumerate", "zip", "min", "max", "sum", "sorted", "reversed",
    "abs", "round", "any", "all", "filter", "map", "chr", "ord", "isinstance",
    "type", "repr", "format", "slice", "hex", "oct", "bin", "divmod", "pow",
}
_FORBIDDEN = ("__", "import", "open(", "eval(", "exec(")


class CodeNode(BaseNode):
    node_type = "code"
    node_label = "代码执行"
    category = "数据处理"
    description = "执行 Python 片段做数据变换：入参注入局部变量，声明 outputs 后取值返回。"
    params_schema = [
        {
            "name": "inputs",
            "label": "输入变量",
            "type": "multifield",
            "required": False,
            "help": "每个输入：{name: 代码内变量名, selector: 变量选择器（如 llm_1.text）}",
        },
        {
            "name": "code",
            "label": "Python 代码",
            "type": "textarea",
            "required": True,
            "help": "可直接用 inputs 定义的变量名；最后给 outputs 声明的变量名赋值即可返回。禁用 import/eval/open。",
        },
        {
            "name": "outputs",
            "label": "输出变量",
            "type": "multifield",
            "required": True,
            "help": "每个输出：{name}，执行后从局部作用域取同名变量值返回",
        },
    ]
    outputs_desc = {"<输出名>": "代码内同名变量的值"}

    def _run(self, pool, db, inputs: dict) -> NodeResult:
        code = self.params.get("code") or ""
        if not code.strip():
            return NodeResult(status="failed", error="代码为空")
        low = code.replace(" ", "").replace("\t", "")
        for bad in _FORBIDDEN:
            if bad in low:
                return NodeResult(status="failed", error=f"代码包含禁用关键字: {bad}")

        local = {}
        for d in self.params.get("inputs") or []:
            if not isinstance(d, dict):
                continue
            name = d.get("name")
            sel = d.get("selector") or d.get("variable_selector")
            if name and sel:
                local[name] = pool.resolve_value(sel)
        out_defs = [d for d in (self.params.get("outputs") or []) if isinstance(d, dict)]
        for d in out_defs:
            if d.get("name"):
                local[d["name"]] = None

        safe_builtins = {n: getattr(builtins, n) for n in _SAFE_BUILTIN_NAMES}
        safe_builtins["print"] = lambda *a, **k: None  # 打印不泄漏到日志
        glob = {"__builtins__": safe_builtins}
        try:
            exec(compile(code, "<workflow_code>", "exec"), glob, local)
        except Exception as e:  # noqa: BLE001
            # 用户代码报错 → 转 failed 结果。必须 log.exception：作者写的片段有 bug 时，
            # SSE 只显示一行错误，具体行号/堆栈只有日志能给出（Phase 3.5）
            logger.exception(f"[workflow_engine.code] 代码节点执行失败 node={self.id!r}")
            return NodeResult(status="failed", error=f"代码执行失败: {type(e).__name__}: {e}")

        outputs = {}
        for d in out_defs:
            if d.get("name"):
                outputs[d["name"]] = local.get(d["name"])
        return NodeResult(outputs=outputs)
