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
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.getcode(), resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


class OpenAICompatibleAdapter(BaseModelAdapter):
    def _payload(self, messages, **params):
        payload = {
            "model": self.config.get("model_name", ""),
            "messages": messages,
            "temperature": params.get("temperature", self.config.get("temperature", 0.4)),
            "top_p": params.get("top_p", self.config.get("top_p", 0.9)),
            "max_tokens": params.get("max_tokens", self.config.get("max_tokens", 6000)),
            "stream": False,
        }
        # 思考模式控制：OpenAI 兼容协议下，通过 chat_template_kwargs 开启/关闭思考
        # （Ollama 的 qwen3 等本地 thinking 模型依赖此参数）。默认开启。
        thinking = self.config.get("enable_thinking", True)
        if thinking is False:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        elif thinking is True:
            payload["chat_template_kwargs"] = {"enable_thinking": True}
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
        payload = {
            "model": self.config.get("model_name", ""),
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 4,
            "stream": False,
        }
        status, _ = _http_post(self.config.get("api_base", ""), self.config.get("api_key", ""), payload)
        return status == 200
