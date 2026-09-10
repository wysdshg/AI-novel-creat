"""LLM 节点：调用大模型生成文本（复用 get_adapter + 防复读解码参数）。

⚠️ 流式端点/线程池环境约束见 base.py 头部铁律——本节点只用传入的独立 db。
"""
from typing import Optional

from ..base import BaseNode, NodeResult


class LLMNode(BaseNode):
    node_type = "llm"
    node_label = "大模型"
    category = "AI 能力"
    description = "调用大模型生成文本：可选模型、温度、思考开关，提示词支持 {{#node.var#}} 变量引用。"
    params_schema = [
        {"name": "model_id", "label": "模型", "type": "string", "required": False,
         "placeholder": "留空 = 使用默认模型"},
        {"name": "temperature", "label": "温度", "type": "number", "default": 0.75,
         "help": "越大越随机；章节/续写类建议 0.6~0.8"},
        {"name": "max_tokens", "label": "最大输出 Tokens", "type": "number", "default": 4096},
        {"name": "enable_thinking", "label": "开启思考", "type": "boolean", "required": False,
         "help": "留空 = 跟随模型配置；ModelScope Qwen3.5 会自动强制关闭"},
        {"name": "system_template", "label": "系统提示词", "type": "textarea", "required": False},
        {"name": "user_template", "label": "用户提示词", "type": "textarea", "required": True},
    ]
    outputs_desc = {"text": "模型生成的文本", "reasoning": "思考内容（模型支持时）"}

    def _run(self, pool, db, inputs: dict) -> NodeResult:
        from app.core.gateway.registry import get_adapter
        from app.models.orm import ModelConfigORM
        from app.services.model_crud import get_default

        from ..common import build_llm_config

        user_prompt = pool.render(self.params.get("user_template") or "")
        if not user_prompt.strip():
            return NodeResult(status="failed", error="用户提示词为空")
        system_prompt = pool.render(self.params.get("system_template") or "")

        model_id = (self.params.get("model_id") or "").strip() or None
        model_orm = None
        if model_id:
            model_orm = db.query(ModelConfigORM).filter_by(id=model_id).first()
        else:
            model_orm = get_default(db)
        if model_orm is None or (model_orm.status or "active") != "active":
            return NodeResult(status="failed", error="未配置可用模型（请在「模型配置」中添加并设为默认）")

        model_cfg = {
            "vendor": model_orm.vendor,
            "api_base": model_orm.api_base,
            "api_key": model_orm.api_key,
            "model_name": model_orm.model_name,
            "temperature": model_orm.temperature,
            "top_p": model_orm.top_p,
            "max_tokens": model_orm.max_tokens,
            "enable_thinking": model_orm.enable_thinking,
        }
        try:
            temperature = float(self.params.get("temperature") if self.params.get("temperature") is not None else 0.75)
        except (TypeError, ValueError):
            temperature = 0.75
        try:
            max_tokens = int(self.params.get("max_tokens") or 4096)
        except (TypeError, ValueError):
            max_tokens = 4096

        config = build_llm_config(
            model_cfg,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_thinking=self.params.get("enable_thinking"),
        )
        adapter = get_adapter(model_orm.vendor, config)

        messages = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        text = adapter.chat(
            messages,
            temperature=temperature,
            enable_thinking=config.get("enable_thinking"),
            max_tokens=max_tokens,
        )
        return NodeResult(outputs={"text": text or "", "reasoning": ""})
