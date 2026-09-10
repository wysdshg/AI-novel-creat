"""统一响应信封（对应 API接口规范.md §0.4）。

所有非流式端点返回: {"code":0,"message":"success","data":...,"trace_id":...}
流式端点（SSE）用 `sse_event()` 产出单帧文本——与信封同一层「统一出网格式」。
"""
import json
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


def sse_event(event: str, payload: Any) -> str:
    """把一条事件编码成 SSE 帧文本（`event:` + `data:` + 空行结尾）。

    流式端点（章节生成 / 商讨 / 工作流执行）共用。**必须用本函数而不是各写一份**：

    - `ensure_ascii=False` 不能漏——否则中文正文全会变成 `\\uXXXX` 转义，
      帧体积翻数倍（长章 ~3000 字会明显拖慢流）；前端 JSON.parse 虽能解，
      但 DevTools 里完全不可读，排查时非常痛苦。
    - 帧尾**必须是空行**（`\\n\\n`）：前端的解析器按 `split('\\n\\n')` 切帧，
      少一个 `\\n` 会把两帧粘成一帧，前一条事件静默丢失。

    ⚠️ 改造前 `chapter.py` / `discussion.py` / `workflow.py` 各存一份逐字相同的实现
    （2026-09-10 Phase 3.4 合并）。
    """
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
