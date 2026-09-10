"""Claude (Anthropic) 适配器。

Anthropic 的 /v1/messages 端点与 OpenAI 不同：system 消息需放在顶层字段，
且 SSE 事件类型为 content_block_delta。其余与 OpenAI 兼容适配器对称实现。
"""
import json
import logging
import urllib.request
import urllib.error

from app.core.gateway.base import BaseModelAdapter

logger = logging.getLogger(__name__)


def _build_request(url: str, payload: dict, api_key: str) -> urllib.request.Request:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-api-key", api_key or "")
    req.add_header("anthropic-version", "2023-06-01")
    return req


def _http_post(api_base: str, api_key: str, payload: dict):
    url = (api_base or "").rstrip("/") + "/messages"
    req = _build_request(url, payload, api_key)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.getcode(), resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        # 网络层异常 → status=-1，调用方抛「模型调用失败(status=-1)」给用户；补日志留痕（Phase 3.5）
        logger.warning(f"[claude] HTTP 请求异常 url={url}: {type(e).__name__}: {e}")
        return -1, str(e)


class ClaudeAdapter(BaseModelAdapter):
    def _payload(self, messages, **params):
        system_parts = []
        msgs = []
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                system_parts.append(content)
            else:
                msgs.append({"role": role, "content": content})
        payload = {
            "model": self.config.get("model_name", ""),
            "max_tokens": params.get("max_tokens", self.config.get("max_tokens", 6000)),
            "messages": msgs,
            "stream": False,
        }
        if system_parts:
            payload["system"] = "\n".join(system_parts)
        return payload

    def chat(self, messages, **params) -> str:
        payload = self._payload(messages, **params)
        status, body = _http_post(self.config.get("api_base", ""), self.config.get("api_key", ""), payload)
        if status != 200:
            raise RuntimeError(f"模型调用失败(status={status}): {body[:300]}")
        data = json.loads(body)
        return "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")

    def stream(self, messages, **params):
        payload = self._payload(messages, **params)
        payload["stream"] = True
        url = (self.config.get("api_base", "") or "").rstrip("/") + "/messages"
        req = _build_request(url, payload, self.config.get("api_key", ""))
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    try:
                        obj = json.loads(data)
                    except Exception as e:  # noqa: BLE001
                        # 容错跳过单帧，但留痕（Phase 3.5）
                        logger.warning(
                            f"[claude.stream] 跳过无法解析的 SSE 帧: "
                            f"{type(e).__name__}: {e}; data={data[:200]!r}"
                        )
                        continue
                    if obj.get("type") == "content_block_delta":
                        text = obj.get("delta", {}).get("text", "")
                        if text:
                            yield text
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")
            yield f"\n[模型调用失败 status={e.code}: {detail[:200]}]"
        except Exception as e:  # noqa: BLE001
            # 流式失败时前端只拿到一句短文案，服务端必须留堆栈（Phase 3.5）
            logger.exception(f"[claude.stream] 流式调用异常 model={self.config.get('model_name')!r}")
            yield f"\n[模型调用异常: {str(e)[:200]}]"

    async def astream(self, messages, **params):
        for chunk in self.stream(messages, **params):
            yield chunk

    def test_connection(self) -> bool:
        payload = {
            "model": self.config.get("model_name", ""),
            "max_tokens": 4,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
        }
        status, _ = _http_post(self.config.get("api_base", ""), self.config.get("api_key", ""), payload)
        return status == 200
