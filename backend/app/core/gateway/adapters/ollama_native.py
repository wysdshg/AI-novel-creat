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
import logging
import urllib.request
import urllib.error

from app.core.gateway.base import BaseModelAdapter

logger = logging.getLogger(__name__)


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


# Ollama 运行时默认 num_ctx 仅 2048 token（与模型自身 context_length 无关！），
# 超出部分会被「从最老的 token 开始」静默丢弃 —— 即 system prompt 开头（世界观 /
# 官制等权威设定）最先被砍掉，模型看到残缺上下文却毫无报错。
# 实测：5969 字符的 system prompt，不传 num_ctx 时 prompt_eval_count 仅 2050，
# 官制设定全丢；传 num_ctx=16384 后为 4827，回答立刻正确。
#
# 章节生成走 BUDGET_LEVELS["standard"] = 32000 token，固定 16384 仍会截断，
# 因此按实际 messages 长度动态放大窗口：短对话省显存、长上下文自动够用。
_MIN_NUM_CTX = 8192
_MAX_NUM_CTX = 65536


def _estimate_tokens(messages) -> int:
    """粗估 messages 的 token 数。

    中文约 1 字 ≈ 0.6~1 token，这里按 1 char = 1 token 保守估（宁可窗口开大，
    也不能让上下文被静默截断）。每条消息再补 8 token 的角色/分隔开销。
    """
    total = 0
    for m in messages or []:
        total += len(str((m or {}).get("content", ""))) + 8
    return total


def _fit_num_ctx(messages, num_predict: int) -> int:
    """按需求量向上取到 2 的幂，并夹在 [_MIN_NUM_CTX, _MAX_NUM_CTX]。"""
    need = _estimate_tokens(messages) + max(int(num_predict or 0), 512) + 512
    ctx = _MIN_NUM_CTX
    while ctx < need and ctx < _MAX_NUM_CTX:
        ctx *= 2
    return min(ctx, _MAX_NUM_CTX)


class OllamaNativeAdapter(BaseModelAdapter):
    def _opts(self, messages=None, **params):
        """组装 Ollama 原生 options。

        注意与 OpenAI 兼容层的参数名差异：
        - 生成长度是 num_predict，不是 max_tokens（传 max_tokens 会被静默忽略）；
        - 上下文窗口是 num_ctx，不传就退化成 2048，必须显式给足。
        """
        opts: dict = {}

        temperature = params.get("temperature")
        if temperature is None:
            temperature = self.config.get("temperature")
        if temperature is not None:
            opts["temperature"] = temperature

        top_p = params.get("top_p")
        if top_p is None:
            top_p = self.config.get("top_p")
        if top_p is not None:
            opts["top_p"] = top_p

        # 重复惩罚：专治小模型长文本复读循环（数值越大越抑制重复，1.0=关闭）。
        # 章节生成长文本默认 1.3（chapter.py 按 vendor 注入 config）。
        repeat_penalty = params.get("repeat_penalty")
        if repeat_penalty is None:
            repeat_penalty = self.config.get("repeat_penalty")
        if repeat_penalty is not None:
            opts["repeat_penalty"] = float(repeat_penalty)

        # 生成上限：Ollama 原生用 num_predict
        max_tokens = params.get("max_tokens")
        if max_tokens is None:
            max_tokens = self.config.get("max_tokens")
        if max_tokens:
            opts["num_predict"] = int(max_tokens)

        # 上下文窗口：必须显式设置，否则长 system prompt 会被静默截断。
        # 优先级：显式入参 > 模型配置 > 按 messages 实际长度动态推算。
        num_ctx = params.get("num_ctx") or self.config.get("num_ctx")
        if not num_ctx:
            num_ctx = _fit_num_ctx(messages, opts.get("num_predict", 2048))
        opts["num_ctx"] = int(num_ctx)

        return opts

    def _chat_url(self) -> str:
        return f"{_ollama_root(self.config.get('api_base', ''))}/api/chat"

    def _tags_url(self) -> str:
        return f"{_ollama_root(self.config.get('api_base', ''))}/api/tags"

    def _stream(self, messages, think: bool, **params):        # noqa: C901
        """原生流式。think=false 产出 content，think=true 产出 thinking。"""
        url = self._chat_url()
        payload = {
            "model": self.config.get("model_name", ""),
            "messages": messages,
            "stream": True,
            "think": think,
            "cache_prompt": True,  # 稳定前缀（system+目录）KV 复用，前缀重传成本≈0
            "options": self._opts(messages, **params),
        }

        req = _build_request(url, payload, self.config.get("api_key", ""))
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception as e:  # noqa: BLE001
                        # Ollama 每行一个 JSON（NDJSON）；容错跳过畸形行，但留痕（Phase 3.5）
                        logger.warning(
                            f"[ollama.stream] 跳过无法解析的 NDJSON 行: "
                            f"{type(e).__name__}: {e}; line={line[:200]!r}"
                        )
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
            # 流式失败前端只见短语，服务端留堆栈（Phase 3.5）
            logger.exception(f"[ollama.stream] 流式调用异常 model={self.config.get('model_name')!r}")
            yield f"\n[模型调用异常: {str(e)[:200]}]"

    def stream(self, messages, **params):
        """流式返回干净回答（think=false），用于正文 / 对话回复。"""
        yield from self._stream(messages, think=False, **params)

    def stream_thinking(self, messages, **params):
        """流式返回思考过程（think=true），用于「思考过程」展示。"""
        yield from self._stream(messages, think=True, **params)

    def stream_with_thinking(self, messages, **params):
        """流式返回「思考 + 正文」两种片段（供思考可见化展示）。

        think=true 时 Ollama 原生响应可能同时携带 message.thinking 与 message.content：
        - thinking 片段 → ("thinking", t)
        - content 片段 → ("content", c)
        """
        url = self._chat_url()
        payload = {
            "model": self.config.get("model_name", ""),
            "messages": messages,
            "stream": True,
            "think": True,
            "cache_prompt": True,  # 稳定前缀 KV 复用
            "options": self._opts(messages, **params),
        }
        req = _build_request(url, payload, self.config.get("api_key", ""))
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception as e:  # noqa: BLE001
                        # 同 _stream：容错跳过畸形 NDJSON 行，但留痕（Phase 3.5）
                        logger.warning(
                            f"[ollama.stream_with_thinking] 跳过无法解析的 NDJSON 行: "
                            f"{type(e).__name__}: {e}; line={line[:200]!r}"
                        )
                        continue
                    msg = obj.get("message") or {}
                    t = msg.get("thinking") or ""
                    if t:
                        yield ("thinking", t)
                    c = msg.get("content") or ""
                    if c:
                        yield ("content", c)
                    if obj.get("done"):
                        break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")
            yield ("content", f"\n[模型调用失败 status={e.code}: {detail[:200]}]")
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[ollama.stream_with_thinking] 流式调用异常 model={self.config.get('model_name')!r}")
            yield ("content", f"\n[模型调用异常: {str(e)[:200]}]")

    def chat(self, messages, **params) -> str:
        url = self._chat_url()
        payload = {
            "model": self.config.get("model_name", ""),
            "messages": messages,
            "stream": False,
            "think": False,
            "cache_prompt": True,  # 稳定前缀 KV 复用
            "options": self._opts(messages, **params),
        }
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
        except Exception as e:  # noqa: BLE001
            # 「测试连接」失败要留痕：UI 只显示"连接失败"，日志才能说明是拒绝了还是连不上（Phase 3.5）
            logger.warning(f"[ollama.test_connection] 连接测试失败: {type(e).__name__}: {e}")
            return False
