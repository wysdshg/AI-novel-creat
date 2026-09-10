"""一次性探测：魔搭 GLM-5.3-Flash 流式响应里 content 与 reasoning_content 的分布。

探测 A：裸请求（复刻后端 vendor=custom 的实际 payload——不发任何思考字段）
探测 B：带顶层 thinking.type=disabled（测魔搭是否认智谱风格的思考控制字段）

2026-09-10 实测结论（已固化 docs/04-B13）：
- A：773 帧，reasoning_content 1418 字（正文全在其中），content_len=0
- B：thinking.type 被魔搭静默忽略（不报错也不生效），content 仍为 0
运行前设置环境变量 MS_API_KEY（勿把 token 写进本文件）。
"""
import json
import os
import urllib.request

BASE = "https://api-inference.modelscope.cn/v1/chat/completions"
KEY = os.environ.get("MS_API_KEY", "")


def probe(tag, extra_payload=None):
    body = {
        "model": "ZhipuAI/GLM-5.3-Flash",
        "messages": [{"role": "user", "content": "写一段80字左右的武侠打斗场面，直接开始。"}],
        "stream": True,
        "max_tokens": 800,
    }
    if extra_payload:
        body.update(extra_payload)
    req = urllib.request.Request(
        BASE, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
        method="POST")
    reason_len = content_len = 0
    tail_r = tail_c = ""
    frames = 0
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"]
                except Exception:
                    continue
                frames += 1
                r = delta.get("reasoning_content") or ""
                c = delta.get("content") or ""
                if r:
                    reason_len += len(r)
                    tail_r = (tail_r + r)[-50:]
                if c:
                    content_len += len(c)
                    tail_c = (tail_c + c)[-50:]
    except urllib.error.HTTPError as e:
        print(f"[{tag}] HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
        return
    print(f"[{tag}] frames={frames} reasoning_len={reason_len} content_len={content_len}")
    print(f"  reasoning_tail: {tail_r!r}")
    print(f"  content_tail:   {tail_c!r}")


probe("A-裸请求(复刻后端)")
probe("B-thinking.type=disabled", {"thinking": {"type": "disabled"}})
