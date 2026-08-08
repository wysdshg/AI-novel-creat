"""导入各厂商适配器并触发 @register 自注册。

本模块被 app/core/gateway/__init__.py 导入，确保任意 `from app.core.gateway.registry
import get_adapter` 时所有适配器均已注册。
"""
from app.core.gateway.adapters.openai_compat import OpenAICompatibleAdapter
from app.core.gateway.adapters.claude import ClaudeAdapter
from app.core.gateway.adapters.ollama_native import OllamaNativeAdapter
from app.core.gateway.registry import register

# 所有 OpenAI 兼容端点的厂商共用同一适配器（用户需在 api_base 指向其兼容地址）
for _vendor in (
    "openai", "deepseek", "qwen", "kimi", "ollama", "custom", "ernie", "spark",
    # 以下三家均为 OpenAI 兼容协议：
    "siliconflow",   # 硅基流动
    "nvidia",        # 英伟达 NIM
    "zhipu",         # 智谱 GLM
):
    register(_vendor)(OpenAICompatibleAdapter)

register("claude")(ClaudeAdapter)

# Ollama 本地思考模型经 OpenAI 兼容端点无法可靠返回 content，改用原生 /api/chat。
# 覆盖上面循环中为 "ollama" 注册的 OpenAICompatibleAdapter。
register("ollama")(OllamaNativeAdapter)
