"""Ollama 原生适配器（/api/chat）。

为什么需要它：本地 qwen3.x GGUF 经 OpenAI 兼容 /v1/chat/completions 流式输出时，
思考过程（约 13k+ 字）全部落在 delta.reasoning，而真正的「回答」很少可靠地进入
delta.content（常为空），导致章节正文与对话回复为空。

Ollama 原生 /api/chat 端点对思考模型支持良好：
- think=false → message.content 即干净回答，无思考文本（快速、可靠）；
- think=true  → message.thinking 为思考过程，message.content 通常为空（回答含在思考末尾）。

因此：
- stream()       始终用 think=false，yield 干净的 content 片段（供正文/回复）；
- stream_thinking() 用 think=true，yield thinking 片段（供「思考过程」展示，可选）。
- chat()         非流式 think=false，返回完整干净文本。
"""
import json
import urllib.request
import urllib.error

from app.core.gateway.base import BaseModelAdapter


def _ollama_root(api_base: str) -> str:
    """从配置里的 api_base（多为 .../v1）推导 Ollama 根地址。"""
    base = (api_base or "http://localhost:11434/v1").rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    if not base:
        base = "http://localhost:11434"
    return base


def _build_request(url: str, payload: dict, api_key: str) -> urllib.request.Request:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    return req


class OllamaNativeAdapter(BaseModelAdapter):
    def _opts(self, **params):
        opts = {}
        if params.get("temperature") is not None:
            opts["temperature"] = params["temperature"]
        if params.get("top_p") is not None:
            opts["top_p"] = params["top_p"]
        if params.get("max_tokens") is not None:
            opts["max_tokens"] = params["max_tokens"]
        return opts

    def _chat_url(self) -> str:
        return f"{_ollama_root(self.config.get('api_base', ''))}/api/chat"

    def _tags_url(self) -> str:
        return f"{_ollama_root(self.config.get('api_base', ''))}/api/tags"

    def _stream(self, messages, think: bool, **params):
        """原生流式。think=false 产出 content，think=true 产出 thinking。"""
        url = self._chat_url()
        payload = {
            "model": self.config.get("model_name", ""),
            "messages": messages,
            "stream": True,
            "think": think,
        }
        opts = self._opts(**params)
        if opts:
            payload["options"] = opts
        elif self.config.get("temperature") is not None:
            payload["options"] = {"temperature": self.config.get("temperature")}

        req = _build_request(url, payload, self.config.get("api_key", ""))
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:  # noqa: BLE001
                        continue
                    msg = obj.get("message") or {}
                    if think:
                        piece = msg.get("thinking") or ""
                    else:
                        piece = msg.get("content") or ""
                    if piece:
                        yield piece
                    if obj.get("done"):
                        break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")
            yield f"\n[模型调用失败 status={e.code}: {detail[:200]}]"
        except Exception as e:  # noqa: BLE001
            yield f"\n[模型调用异常: {str(e)[:200]}]"

    def stream(self, messages, **params):
        """流式返回干净回答（think=false），用于正文 / 对话回复。"""
        yield from self._stream(messages, think=False, **params)

    def stream_thinking(self, messages, **params):
        """流式返回思考过程（think=true），用于「思考过程」展示。"""
        yield from self._stream(messages, think=True, **params)

    def chat(self, messages, **params) -> str:
        url = self._chat_url()
        payload = {
            "model": self.config.get("model_name", ""),
            "messages": messages,
            "stream": False,
            "think": False,
        }
        opts = self._opts(**params)
        if opts:
            payload["options"] = opts
        elif self.config.get("temperature") is not None:
            payload["options"] = {"temperature": self.config.get("temperature")}
        req = _build_request(url, payload, self.config.get("api_key", ""))
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return (data.get("message") or {}).get("content") or ""
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"模型调用失败(status={e.code}): {e.read().decode('utf-8','ignore')[:300]}") from e
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"解析模型响应失败: {str(e)[:300]}") from e

    async def astream(self, messages, **params):
        for chunk in self.stream(messages, **params):
            yield chunk

    def test_connection(self) -> bool:
        try:
            req = _build_request(self._tags_url(), {}, self.config.get("api_key", ""))
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.getcode() == 200
        except Exception:  # noqa: BLE001
            return False
