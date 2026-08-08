"""统一响应信封（对应 API接口规范.md §0.4）。

所有非流式端点返回: {"code":0,"message":"success","data":...,"trace_id":...}
"""
import uuid
from typing import Any


def _trace() -> str:
    return uuid.uuid4().hex[:8]


def ok(data: Any = None, message: str = "success") -> dict:
    return {"code": 0, "message": message, "data": data, "trace_id": _trace()}


def fail(code: int, message: str, data: Any = None) -> dict:
    return {"code": code, "message": message, "data": data, "trace_id": _trace()}


def not_implemented(feature: str = "该功能") -> dict:
    """脚手架阶段常态：接口未实现。"""
    return fail(50101, f"{feature}尚未实现（脚手架阶段）")


def paginated(items: list, total: int, page: int = 1, page_size: int = 20) -> dict:
    """列表分页包装（§0.5）。"""
    return {"items": items, "total": total, "page": page, "page_size": page_size}
