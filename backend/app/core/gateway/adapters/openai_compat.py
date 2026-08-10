"""OpenAI 兼容适配器。

覆盖厂商：openai / deepseek / qwen / kimi / ollama / custom / ernie / spark /
siliconflow（硅基流动）/ nvidia（英伟达 NIM）/ zhipu（智谱 GLM）。
这些厂商均提供与 OpenAI 一致的 /chat/completions 端点（部分需在 api_base 指向其兼容地址）。

实现原则：
- 仅用标准库 urllib，零第三方依赖，避免污染隔离 venv。
- chat() 同步返回完整文本；stream() 同步生成器逐段 yield（供章节生成 SSE 使用）；
  astream() 异步包装 stream() 以满足抽象基类接口。
"""
import json
import urllib.request
import urllib.error

from app.core.gateway.base import BaseModelAdapter


def _build_request(url: str, payload: dict, api_key: str) -> urllib.request.Request:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    return req


def _http_post(api_base: str, api_key: str, payload: dict):
    """返回 (status:int, body:str)。"""
    base = (api_base or "").rstrip("/")
    url = f"{base}/chat/completions"
    req = _build_request(url, payload, api_key)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.getcode(), resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


class OpenAICompatibleAdapter(BaseModelAdapter):
    # 仅这些厂商的 OpenAI 兼容端点认 chat_template_kwargs 这一非标准扩展字段
    _CHAT_TEMPLATE_KWARGS_VENDORS = {"qwen", "nvidia"}
    # 这些厂商用顶层 thinking.type 控制思考（OpenAI SDK 里走 extra_body，裸 HTTP 即顶层字段）
    _THINKING_FIELD_VENDORS = {"deepseek", "zhipu"}
    # OpenAI 推理模型（o1/o3/o4 系列）用 max_completion_tokens，且不支持 temperature/top_p
    _OPENAI_REASONING_PREFIXES = ("o1", "o3", "o4")

    def _payload(self, messages, **params):
        # 思考开关：本次请求参数 > 模型配置 > True
        enable_thinking = params.get("enable_thinking")
        if enable_thinking is None:
            enable_thinking = self.config.get("enable_thinking", True)

        vendor = (self.config.get("vendor") or "").lower()
        model = (self.config.get("model_name") or "").lower()
        max_tokens = params.get("max_tokens", self.config.get("max_tokens", 6000))

        payload = {
            "model": self.config.get("model_name", ""),
            "messages": messages,
            "temperature": params.get("temperature", self.config.get("temperature", 0.4)),
            "top_p": params.get("top_p", self.config.get("top_p", 0.9)),
            "max_tokens": max_tokens,
            "stream": False,
        }

        # ── 思考模式字段：各厂商差异巨大，混用非标准字段会直接 400 ──
        if vendor in self._CHAT_TEMPLATE_KWARGS_VENDORS:
            # Qwen / NVIDIA(NIM-GLM)：认 chat_template_kwargs.enable_thinking
            payload["chat_template_kwargs"] = {"enable_thinking": bool(enable_thinking)}
        elif vendor == "deepseek":
            # DeepSeek：顶层 thinking.type；disabled 仅在 reasoning_effort=low 时合法
            if enable_thinking:
                payload["thinking"] = {"type": "enabled"}
            else:
                payload["thinking"] = {"type": "disabled"}
                payload["reasoning_effort"] = "low"
        elif vendor == "zhipu":
            # 智谱 GLM-4.5+：顶层 thinking.type（enabled/disabled 均支持）
            payload["thinking"] = {"type": "enabled" if enable_thinking else "disabled"}
        # 其余厂商（openai/kimi/ernie/spark/siliconflow/custom/ollama）：不发送任何思考控制字段，
        # 使用厂商默认行为，避免 “additional properties not allowed” 400。

        # ── OpenAI 推理模型特例 ──
        if vendor == "openai" and model.startswith(self._OPENAI_REASONING_PREFIXES):
            # o1/o3/o4 用 max_completion_tokens（max_tokens 会 TypeError），且不接受 temperature/top_p
            payload.pop("max_tokens", None)
            payload["max_completion_tokens"] = max_tokens
            payload.pop("temperature", None)
            payload.pop("top_p", None)

        # ===== 调试日志：真正发给模型的请求体（发送前打印）=====
        try:
            def _cut(s, n=300):
                if not isinstance(s, str):
                    s = str(s)
                return s if len(s) <= n else s[:n] + f"…(共{len(s)}字)"
            print("\n===== [DEBUG] LLM 请求体 =====", flush=True)
            print(f"  vendor={vendor!r} model={self.config.get('model_name')!r} stream={payload.get('stream')}", flush=True)
            print(f"  url={(self.config.get('api_base','') or '').rstrip('/')}/chat/completions", flush=True)
            print(f"  messages 条数={len(messages)}", flush=True)
            for i, m in enumerate(messages):
                role = m.get("role")
                c = m.get("content", "")
                if isinstance(c, list):
                    c = str(c)
                # system 提示词（可能上万字）不截断，便于排查；其余消息截断到 300 字
                limit = 20000 if role == "system" else 300
                print(f"  [{i}] {role}: {_cut(c, limit)}", flush=True)
            extra = {k: v for k, v in payload.items() if k not in ("model", "messages", "stream")}
            print(f"  其他参数={extra}", flush=True)
            print("===== [DEBUG] END =====\n", flush=True)
        except Exception:
            pass

        return payload

    def chat(self, messages, **params) -> str:
        payload = self._payload(messages, **params)
        status, body = _http_post(self.config.get("api_base", ""), self.config.get("api_key", ""), payload)
        if status != 200:
            raise RuntimeError(f"模型调用失败(status={status}): {body[:300]}")
        try:
            data = json.loads(body)
            msg = data["choices"][0]["message"]
            # content 即正文；reasoning/thinking 是思考过程，不混入正文
            return msg.get("content") or ""
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"解析模型响应失败: {body[:300]}") from e

    def stream(self, messages, **params):
        payload = self._payload(messages, **params)
        payload["stream"] = True
        base = (self.config.get("api_base", "") or "").rstrip("/")
        url = f"{base}/chat/completions"
        req = _build_request(url, payload, self.config.get("api_key", ""))
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        delta = obj["choices"][0]["delta"]
                        # content 即正文；reasoning/reasoning_content 是思考过程，忽略
                        piece = delta.get("content") or ""
                        if piece:
                            yield piece
                    except Exception:  # noqa: BLE001
                        continue
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")
            yield f"\n[模型调用失败 status={e.code}: {detail[:200]}]"
        except Exception as e:  # noqa: BLE001
            yield f"\n[模型调用异常: {str(e)[:200]}]"

    async def astream(self, messages, **params):
        for chunk in self.stream(messages, **params):
            yield chunk

    def test_connection(self) -> bool:
        payload = self._payload([{"role": "user", "content": "hi"}], max_tokens=1)
        status, _ = _http_post(self.config.get("api_base", ""), self.config.get("api_key", ""), payload)
        return status == 200
