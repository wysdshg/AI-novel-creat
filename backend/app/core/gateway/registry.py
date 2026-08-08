"""模型厂商注册表（多厂商热插拔）。

新增厂商：在此 import 并加入 REGISTRY 即可，无需改动调用方。
"""
from typing import Dict, Type
from app.core.gateway.base import BaseModelAdapter


REGISTRY: Dict[str, Type[BaseModelAdapter]] = {}


def register(vendor: str):
    def deco(cls: Type[BaseModelAdapter]):
        REGISTRY[vendor] = cls
        cls.vendor = vendor
        return cls
    return deco


def get_adapter(vendor: str, config: dict) -> BaseModelAdapter:
    cls = REGISTRY.get(vendor)
    if not cls:
        raise ValueError(f"未注册的模型厂商: {vendor}（请在 gateway/registry.py 注册）")
    return cls(config)


# 内置占位实现，演示注册方式（真实厂商适配器后续在此扩展）
@register("placeholder")
class PlaceholderAdapter(BaseModelAdapter):
    def chat(self, messages, **params) -> str:
        return "[placeholder] 模型未接入"

    async def astream(self, messages, **params):
        yield "[placeholder] 模型未接入"
        return

    def test_connection(self) -> bool:
        return False
