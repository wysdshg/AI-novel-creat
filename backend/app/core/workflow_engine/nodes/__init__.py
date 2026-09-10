"""节点注册表：新增节点 = 实现 BaseNode 子类 + 在此登记。"""
from .chapter import ChapterNode
from .code import CodeNode
from .end import EndNode
from .ifelse import IfElseNode
from .llm import LLMNode
from .setting_retrieval import SettingRetrievalNode
from .start import StartNode
from .template import TemplateNode

NODE_CLASSES = [
    StartNode,
    EndNode,
    LLMNode,
    SettingRetrievalNode,
    IfElseNode,
    CodeNode,
    TemplateNode,
    ChapterNode,
]

NODE_CLASS_BY_TYPE = {c.node_type: c for c in NODE_CLASSES}


def make_node(raw: dict):
    """按节点的 type 字段实例化节点；未知类型抛错（画布侧应只允许注册过的类型）。"""
    node_type = (raw or {}).get("type") or "generic"
    cls = NODE_CLASS_BY_TYPE.get(node_type)
    if cls is None:
        raise ValueError(f"未知节点类型: {node_type}")
    return cls(raw)
