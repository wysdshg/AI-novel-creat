"""参考文件「选择阶段」策略层（按需加载机制）。

按需加载分两阶段：
  Pass1: 让模型决定是否需要参考文件 -> 产出 selected_ids
  Pass2: fetch_refs_by_ids(db, ids) 注入正文 -> 流式作答

本模块只抽象「Pass1 -> selected_ids」这一步，提供两种策略：
  - MarkerSelection (A): 解析约定文本 LOAD_REFS:<ids>
        通用、对任何能吐文字的模型都 work（本地 4b / OpenAI / Claude 均可）。现状默认。
  - ToolCallSelection (B): 解析原生 tool_calls（retrieve_refs 工具）
        强 API（OpenAI/Claude）原生 function-calling，结构化、最稳。★ 占位未启用 ★

两者都只产出 selected_ids: list[str] | None，之后的 fetch/inject/Pass2 流程完全共用，
因此切换策略是「插拔」，不动主链路。

切换方式（未来）：把环境变量 NA_REF_SELECTOR 设为 toolcall，并实现 ToolCallSelection.select。
"""
from typing import List, Optional

from app.services import reference_crud as ref_svc
from app.core.gateway.base import BaseModelAdapter


class ReferenceSelection:
    """选择阶段策略接口：给定 Pass1 输出，解析出要加载的参考 id 列表。

    select() 返回 None 表示「模型判断无需参考、直接作答」；
    返回 list 表示「需要加载这些 id」。
    """

    def select(
        self,
        first_text: str,
        *,
        adapter: Optional[BaseModelAdapter] = None,
        raw: object = None,
    ) -> Optional[List[str]]:
        raise NotImplementedError


class MarkerSelection(ReferenceSelection):
    """策略 A（现状默认）：从模型文本里抠 LOAD_REFS 约定标记。

    适用：任何模型（本地 4b / OpenAI / Claude 均通用）。
    解析逻辑见 reference_crud.parse_load_refs（正则 + 容错）。
    """

    def select(
        self,
        first_text: str,
        *,
        adapter: Optional[BaseModelAdapter] = None,
        raw: object = None,
    ) -> Optional[List[str]]:
        return ref_svc.parse_load_refs(first_text)


class ToolCallSelection(ReferenceSelection):
    """策略 B（占位 / 未启用）：解析原生 tool_calls。

    ★ 目前未实现——请勿在 NA_REF_SELECTOR=toolcall 前启用，否则 select() 抛 NotImplementedError。

    未来实现要点（当 adapter 支持 tool_calls 时）：
      1. 在适配器 chat() 中保留 tool_calls 原始响应（当前 chat() 只返回纯文本 str，需扩展
         为可选返回 (text, tool_calls) 或新增 chat_with_tools()）。
      2. 定义工具 schema：retrieve_refs(ids: list[str])。
      3. 此处从 raw 里取 tool_calls[].function：
           - name == "retrieve_refs" -> arguments.get("ids", [])
           - 用 ref_svc.fetch_refs_by_ids(db, ids) 校验 id 有效性（同 Marker 路径）。
      4. 把 retrieve_refs 的调用结果作为 tool 消息回灌，再让模型续答（即现有 Pass2）。

    注意：无论 A 还是 B，selected_ids 之后的 fetch/inject/Pass2 完全共用，无需重写。
    """

    TOOL_NAME = "retrieve_refs"

    def select(
        self,
        first_text: str,
        *,
        adapter: Optional[BaseModelAdapter] = None,
        raw: object = None,
    ) -> Optional[List[str]]:
        raise NotImplementedError(
            "ToolCallSelection 尚未实现：需要适配器暴露 tool_calls 并定义 "
            "retrieve_refs(ids=[...]) 工具。当前请保持 NA_REF_SELECTOR=marker（策略 A）。"
        )


def get_reference_selector(mode: Optional[str] = None) -> ReferenceSelection:
    """按模式取选择策略。优先级：参数 > 环境变量 NA_REF_SELECTOR > 默认 marker(A)。"""
    mode = (mode or "").lower() or (os_environ_mode())
    if mode == "toolcall":
        return ToolCallSelection()
    # 默认及未知值一律回退到 A，保证现状行为不变
    return MarkerSelection()


def os_environ_mode() -> str:
    import os

    return os.environ.get("NA_REF_SELECTOR", "marker").lower()
