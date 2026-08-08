"""模型适配器抽象基类（关键扩展点，对应 API接口规范.md §4.4）。

新增厂商 = 继承 BaseModelAdapter 实现三个方法 + 在 registry 注册 vendor 字符串，
引擎层无需改动。当前为接口契约，不做真实 HTTP 调用。
"""
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, List, Dict


class BaseModelAdapter(ABC):
    vendor: str = "base"

    def __init__(self, config: Dict[str, Any]):
        self.config = config  # 含 api_base / api_key / model_name / temperature 等

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **params) -> str:
        """同步对话，返回完整文本。"""
        raise NotImplementedError

    @abstractmethod
    async def astream(self, messages: List[Dict[str, str]], **params) -> AsyncIterator[str]:
        """流式对话，逐段 yield 文本。章节生成使用。"""
        raise NotImplementedError
        yield  # pragma: no cover

    @abstractmethod
    def test_connection(self) -> bool:
        """测试连通性，对应 POST /models/test。"""
        raise NotImplementedError
