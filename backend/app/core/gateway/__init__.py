"""模型网关包：多厂商统一适配（需求 7）。

导入 adapters 子包以触发各厂商适配器的 @register 自注册，
使 `from app.core.gateway.registry import get_adapter` 时 REGISTRY 已就绪。
"""
from app.core.gateway import adapters  # noqa: F401  触发适配器自注册

__all__ = ["adapters"]
