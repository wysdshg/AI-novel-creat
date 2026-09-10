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
        # Phase 4.2（token 计量）：最近一次调用的用量。
        # 用**属性**传出而不是改返回值 —— 因为 stream()/astream() 是生成器，
        # 无法 return 值，改签名又会波及所有调用方（chapter/discussion/ingestion…）。
        # 统一格式：{"prompt_tokens": int, "completion_tokens": int,
        #           "total_tokens": int, "estimated": bool}
        # 保持 None 表示"本次厂商没返回用量"，调用方可退化为按字符估算。
        self.last_usage: Dict[str, Any] | None = None

    @staticmethod
    def normalize_usage(
        raw: Any,
        *,
        prompt_key: str = "prompt_tokens",
        completion_key: str = "completion_tokens",
    ) -> Dict[str, Any] | None:
        """把各厂商五花八门的用量字段归一成统一结构。

        - OpenAI 兼容：`prompt_tokens` / `completion_tokens`
        - Claude：`input_tokens` / `output_tokens`
        - Ollama：`prompt_eval_count` / `eval_count`

        两边都取不到时返回 None（不硬造 0，避免把"没数据"记成"零消耗"）。
        """
        if not isinstance(raw, dict):
            return None
        p = raw.get(prompt_key)
        c = raw.get(completion_key)
        if p is None and c is None:
            return None
        try:
            p = int(p or 0)
            c = int(c or 0)
        except (TypeError, ValueError):
            return None
        return {
            "prompt_tokens": p,
            "completion_tokens": c,
            "total_tokens": int(raw.get("total_tokens") or (p + c)),
            "estimated": False,
        }

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
