"""工作流节点基类（对标 Dify BaseNode）。

每个节点 = BaseNode 子类，实现 _run(pool, db, inputs) 返回 NodeResult。
- run() 是模板方法：统一捕获异常 → failed，并记录实际读取的变量值（调试用）。
- params_schema 声明节点的可配置参数（前端属性面板按它渲染表单）。
- meta() 输出节点目录（GET /workflows/meta/node-types 用）。

⚠️ 铁律（见项目记忆⑥）：节点 _run 内只能用传入的独立 db session，
绝不能访问请求级 get_session() —— 工作流经 SSE 在线程池运行，请求级 session 已关闭。
"""
from typing import Any, Dict, List, Optional


class NodeResult:
    """节点执行结果。"""

    __slots__ = ("status", "outputs", "error", "inputs", "duration_ms")

    def __init__(
        self,
        status: str = "success",       # success / failed
        outputs: Optional[dict] = None,
        error: Optional[str] = None,
        inputs: Optional[dict] = None,
    ):
        self.status = status
        self.outputs = outputs or {}
        self.error = error
        self.inputs = inputs or {}
        self.duration_ms: Optional[int] = None


class BaseNode:
    """节点抽象基类。"""

    node_type = "generic"
    node_label = "节点"
    category = "基础"          # 基础 / AI 能力 / 逻辑控制 / 数据处理 / 小说创作
    description = ""
    # params_schema 元素: {name,label,type,required,default,options,placeholder,help}
    # type: string/number/boolean/select/textarea/variable/multifield
    params_schema: List[dict] = []
    outputs_desc: Dict[str, str] = {}

    def __init__(self, raw: dict):
        self.raw = raw or {}
        self.id: str = (raw or {}).get("id", "")
        self.label: str = (raw or {}).get("label") or self.node_label
        self.params: Dict[str, Any] = (raw or {}).get("params") or {}

    # ---- 模板方法 ----
    def run(self, pool, db) -> NodeResult:
        inputs = self.collect_inputs(pool)
        try:
            result = self._run(pool, db, inputs)
            if not isinstance(result, NodeResult):
                result = NodeResult(outputs={"output": result})
        except Exception as e:  # noqa: BLE001
            result = NodeResult(status="failed", error=f"{type(e).__name__}: {e}")
        result.inputs = inputs
        return result

    # ---- 子类实现 ----
    def _run(self, pool, db, inputs: dict) -> NodeResult:
        raise NotImplementedError

    # ---- 输入收集（调试展示用） ----
    def collect_inputs(self, pool) -> dict:
        """把 params 中所有变量引用（{{#node.var#}} 或 variable 字段）解析成实际值。"""
        out: Dict[str, Any] = {}
        for p in self.params_schema:
            name = p.get("name")
            if not name or name not in self.params:
                continue
            val = self.params[name]
            if p.get("type") == "variable":
                out[name] = pool.resolve_value(val) if isinstance(val, str) else val
            elif isinstance(val, str) and "{{#" in val:
                out[name] = pool.render(val)
        return out

    # ---- 元信息 ----
    @classmethod
    def meta(cls) -> dict:
        return {
            "type": cls.node_type,
            "category": cls.category,
            "label": cls.node_label,
            "description": cls.description,
            "params_schema": cls.params_schema,
            "outputs": cls.outputs_desc,
        }
