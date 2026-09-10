"""探测 C：GLM-5.3-Flash 的 content 是否被 max_tokens 预算卡死。

假设：reasoning 阶段消耗预算，max_tokens 不足时正文（content）被截断为空。
三档对比：800（探测 A/B 原值）/ 4000（≈章节生成实际值 3750）/ 16000。
"""
import json
import os
import sys
import urllib.request

BASE = "https://api-inference.modelscope.cn/v1/chat/completions"
KEY = os.environ.get("MS_API_KEY", "")
if not KEY:
    sys.exit("请先设置环境变量 MS_API_KEY（魔搭访问令牌）")


def probe(tag, max_tokens):
    body = {
        "model": "ZhipuAI/GLM-5.3-Flash",
        "messages": [{"role": "user", "content": "写一段500字左右的武侠打斗场面，直接开始正文，不要解释。"}],
        "stream": True,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        BASE, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"},
        method="POST")
    reason_len = content_len = 0
    finish = None
    tail_c = ""
    frames = 0
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    ch0 = obj["choices"][0]
                    delta = ch0.get("delta") or {}
                except Exception:
                    continue
                frames += 1
                r = delta.get("reasoning_content") or ""
                c = delta.get("content") or ""
                if r:
                    reason_len += len(r)
                if c:
                    content_len += len(c)
                    tail_c = (tail_c + c)[-40:]
                if ch0.get("finish_reason"):
                    finish = ch0["finish_reason"]
    except urllib.error.HTTPError as e:
        print(f"[{tag}] HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}")
        return
    print(f"[{tag}] max_tokens={max_tokens} frames={frames} "
          f"reasoning={reason_len} content={content_len} finish={finish}")
    if tail_c:
        print(f"  content_tail: {tail_c!r}")


for mt in (32768,):
    probe(f"mt={mt}", mt)
