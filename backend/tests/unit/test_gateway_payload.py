"""网关适配器 payload 组装（B 方案：最易崩的第 4 处）。

_openai_compat.OpenAICompatibleAdapter._payload 是纯函数——所有厂商差异
（思考字段形态 / 惩罚注入 / OpenAI o 系特例）都折叠在这里，历史上有过
三次实测翻车（Qwen chat_template_kwargs 污染正文 / nvidia 漏发 thinking /
GLM-5.3-Flash 魔搭正文进 reasoning）。本文件把每种厂商形态固化成用例，
换默认模型时跑一遍即可防退化。
"""
import pytest

from app.core.gateway.adapters.openai_compat import OpenAICompatibleAdapter

MSG = [{"role": "user", "content": "hi"}]


def build_payload(vendor="custom", model="test-model",
                  api_base="http://localhost:9/v1", extra=None, **params):
    cfg = {"vendor": vendor, "model_name": model, "api_base": api_base,
           "api_key": "k", "temperature": 0.4, "top_p": 0.9}
    if extra:
        cfg.update(extra)
    return OpenAICompatibleAdapter(cfg)._payload(MSG, **params)


def test_qwen_vendor_uses_chat_template_kwargs():
    p = build_payload(vendor="qwen", model="qwen3.5-122b")
    assert p["chat_template_kwargs"] == {"enable_thinking": True}
    assert "thinking" not in p  # 思考字段形态唯一，混发会 400


def test_zhipu_vendor_uses_thinking_type():
    p = build_payload(vendor="zhipu", model="glm-4.5", enable_thinking=False)
    assert p["thinking"] == {"type": "disabled"}
    assert "chat_template_kwargs" not in p


def test_nvidia_glm_uses_thinking_type():
    # 历史 bug：nvidia 漏配走 fall-through，强制开思考对 GLM 完全失效
    p = build_payload(vendor="nvidia", model="glm-5.2", enable_thinking=True)
    assert p["thinking"] == {"type": "enabled"}


def test_glm53_flash_on_modelscope_sends_no_thinking_field():
    """GLM-5.3-Flash 适配固化（2026-09-10）。

    默认模型在库里 vendor="custom"（同 Qwen3.8），端点是 ModelScope。
    裸请求 = 厂商默认（魔搭 GLM 默认思考开，reasoning_content 出思考）。
    思考字段发不发都被魔搭静默忽略（实测 thinking.type 不报错也不生效），
    所以正确行为就是 fall-through 不发。
    """
    p = build_payload(vendor="custom", model="ZhipuAI/GLM-5.3-Flash",
                      api_base="https://api-inference.modelscope.cn/v1")
    assert "thinking" not in p
    assert "chat_template_kwargs" not in p


def test_modelscope_qwen38_default_disables_thinking():
    # broken combo 安全网（适配器层第二道防线）：config 显式带 enable_thinking=None
    # 时（模型配置未设置），未在 params 显式指定 → 默认关。
    # 生产第一道防线在 chapter.py 路由层（_broken_thinking_combo 显式算出 False）。
    p = build_payload(vendor="custom", model="Qwen/Qwen3.8-Flash-Next",
                      api_base="https://api-inference.modelscope.cn/v1",
                      extra={"enable_thinking": None})
    assert p["chat_template_kwargs"] == {"enable_thinking": False}


def test_config_without_thinking_key_defaults_on():
    # 文档契约「本次请求参数 > 模型配置 > True」：config 完全不带 key → 厂商默认开
    p = build_payload(vendor="qwen", model="qwen3.5-122b")
    assert p["chat_template_kwargs"] == {"enable_thinking": True}


def test_modelscope_qwen38_explicit_thinking_respected():
    # B11 修复：显式 enable_thinking=True 时尊重（不再强关）
    p = build_payload(vendor="custom", model="Qwen/Qwen3.8-Flash-Next",
                      api_base="https://api-inference.modelscope.cn/v1",
                      enable_thinking=True)
    assert p["chat_template_kwargs"] == {"enable_thinking": True}


def test_penalty_fields_injected_from_config():
    # chapter.py 按模型把惩罚写进 config，payload 必须透传
    p = build_payload(extra={"frequency_penalty": 0.4, "presence_penalty": 0.4})
    assert p["frequency_penalty"] == 0.4
    assert p["presence_penalty"] == 0.4


def test_penalty_omitted_when_not_configured():
    # Qwen3.x 需要惩罚 0 → chapter.py 显式注入 0.0（走 dict.get 默认 None 不发）；
    # 这里验证"未配置就不发字段"，避免把 None 序列化进 JSON 导致 400
    p = build_payload()
    assert "frequency_penalty" not in p
    assert "presence_penalty" not in p


def test_deepseek_disabled_thinking_carries_reasoning_effort():
    p = build_payload(vendor="deepseek", model="deepseek-chat", enable_thinking=False)
    assert p["thinking"] == {"type": "disabled"}
    assert p["reasoning_effort"] == "low"


def test_openai_o_series_uses_max_completion_tokens():
    p = build_payload(vendor="openai", model="o3-mini", max_tokens=1234)
    assert "max_tokens" not in p
    assert p["max_completion_tokens"] == 1234
    assert "temperature" not in p and "top_p" not in p


def test_glm53_penalty_still_standard_fields():
    # GLM-5.3-Flash 走 OpenAI 标准惩罚字段（frequency/presence），不是 ollama 的 repeat_penalty
    p = build_payload(vendor="custom", model="ZhipuAI/GLM-5.3-Flash",
                      api_base="https://api-inference.modelscope.cn/v1",
                      extra={"frequency_penalty": 0.4, "presence_penalty": 0.4})
    assert "repeat_penalty" not in p
    assert p["frequency_penalty"] == 0.4 and p["presence_penalty"] == 0.4
