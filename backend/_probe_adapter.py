import sys, time

sys.path.insert(0, "E:/AI小说创作/backend")
from app.core.gateway.adapters import get_adapter

cfg = {
    "api_base": "http://localhost:11434/v1",
    "api_key": "",
    "model_name": "qwen3.5:4b",
    "temperature": 0.4,
}

t = time.time()
adapter = get_adapter("ollama", cfg)
print("adapter:", type(adapter).__name__, "in", round(time.time() - t, 2), "s")

t = time.time()
out = []
n = 0
for piece in adapter.stream([{"role": "user", "content": "只说收到"}]):
    out.append(piece)
    if n < 3:
        print("piece", n, repr(piece[:60]))
    n += 1
print("FULL:", "".join(out)[:100], "| pieces:", n, "| in", round(time.time() - t, 2), "s")
