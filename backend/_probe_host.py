import urllib.request, json

for host in ["localhost", "127.0.0.1"]:
    url = f"http://{host}:11434/api/chat"
    p = {"model": "qwen3.5:4b", "messages": [{"role": "user", "content": "只说收到"}], "stream": False, "think": False}
    req = urllib.request.Request(url, data=json.dumps(p).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(host, "OK", json.loads(r.read())["message"]["content"])
    except Exception as e:
        print(host, "FAIL", repr(e)[:200])
