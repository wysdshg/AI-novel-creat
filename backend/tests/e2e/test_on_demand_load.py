"""A6 按需加载两阶段协议端到端验收（LOAD_REFS / LOAD_SETTING）。

为什么需要它（用户 2026-09-09 提出）：检索改造完成后，e2e 必须按**真实使用流程**走
——包含「先问 AI 该注入哪些文件，再让它作答」那一轮，而不只是直接生成。

覆盖两条按需加载路径：
  路径 A · 商讨（真两阶段，AI 驱动）
    Pass1 非流式 → 模型输出 `LOAD_REFS:<ids>` / `LOAD_SETTING:<ids>` →
    后端 fetch 正文 → 推 `refs` 事件 → Pass2 流式作答；
    模型若判断无需资料则短路（无 refs 事件，单次调用）。
  路径 B · 章节生成（确定性 top-up，非 AI 驱动）
    `NA_CHAPTER_REF_MODE=hybrid` 时对全局池按相关性补 top-2（见 chapter.py:_global_topup_ids）；
    ctx_meta.refs_loaded_extra 非空。

**防幻觉设计（关键）**：问题里的答案必须"只有资料里才有"，且**不可猜**：
  - 参考文档：剑碑名录第 7 柄的名字（自造词）
  - 设定库  ：灵石兑率 137×64 = 8768 文（任取数字，无通用常识可蒙）
若模型答对 → 证明正文真的被注入；若只答对一半 → 报告 partial。

前置：后端已启动、默认模型可用。hybrid 路径需后端以 `NA_CHAPTER_REF_MODE=hybrid` 启动。

运行：
  cd E:/AI小说创作/backend
  E:/AI小说创作/.venv/Scripts/python.exe tests/e2e/test_on_demand_load.py
可选：
  --base-url / --keep / --skip-hybrid（不测章节 hybrid 路径）
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime

urllib.request.install_opener(
    urllib.request.build_opener(urllib.request.ProxyHandler({})))

# ---- 防幻觉事实（改这里必须同步改下面两处断言）----
STELE_ANSWER = "照胆"                 # 剑碑名录第 7 柄
SPIRIT_STONE_ANSWER = "8768"          # 137 × 64
REF_FILENAME = "太虚剑宗剑碑名录.md"
SETTING_NAME = "灵石货币体系"

REF_CONTENT = f"""# 太虚剑宗·山门剑碑林名录

太虚剑宗山门有七十二柄剑碑，前十二柄为开派祖师亲立，名录如下：

1. 断岳    2. 无咎    3. 藏锋    4. 听雨
5. 拂尘    6. 镇岳    7. {STELE_ANSWER}    8. 寒潭
9. 饮风   10. 抱朴   11. 摧城   12. 归墟

（注：第八柄"寒潭"碑面有裂，第十一柄"摧城"为后补。）
"""

SETTING_DESC = (
    "本世界的灵石货币体系（⚠️ 硬约束，回答数值必须以此为准）：\n"
    "1 上品灵石 = 137 中品灵石；1 中品灵石 = 64 下品灵石；\n"
    "凡俗交易用铜钱，与本体系不直接挂钩。\n"
    "朝廷官市只认可中品及以下灵石，上品灵石严禁流通。"
)

QUESTION = (
    f"两个问题，请一并回答：\n"
    f"① 太虚剑宗山门剑碑林里，第七柄剑碑刻的是什么名字？\n"
    f"② 在我的设定里，一块上品灵石折合多少下品灵石？\n"
    f"（这两个问题都需要查阅我提供的资料/设定，请先加载再答；不要凭猜测回答。）"
)

COMMON_QUESTION = "用一句话说说，写小说时为什么要控制段落长度？"


def http(base, method, path, body=None, timeout=60, stream=False):
    url = base.rstrip("/") + path
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    if stream:
        return resp
    raw = resp.read().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def unwrap(resp, key="data"):
    if isinstance(resp, dict) and key in resp:
        return resp[key]
    return resp


def read_sse(resp):
    event, buf = None, ""
    for raw in resp:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            buf += line[len("data:"):].strip()
        elif line == "":
            if event is not None:
                try:
                    payload = json.loads(buf) if buf else {}
                except json.JSONDecodeError:
                    payload = {"_raw": buf}
                yield event, payload
            event, buf = None, ""


def run_chat(base, pid, question, thinking=False, timeout=300):
    """跑一轮商讨，返回 (事件序列, refs 载荷, 正文, context 载荷)。"""
    events, refs_payload, ctx = [], None, None
    parts = []
    resp = http(base, "POST", f"/api/v1/projects/{pid}/discussion/chat",
                body={"messages": [{"role": "user", "content": question}],
                      "enable_thinking": thinking, "temperature": 0.4},
                timeout=timeout, stream=True)
    try:
        for ev, payload in read_sse(resp):
            if ev != "chunk":
                events.append(ev)
            if ev == "chunk":
                parts.append(payload.get("text", ""))
            elif ev == "refs":
                refs_payload = payload
            elif ev == "context":
                ctx = payload
            elif ev == "done":
                break
    finally:
        resp.close()
    return events, refs_payload, "".join(parts), ctx


def verdict(name, ok, detail=""):
    print(f"   {'✅ PASS' if ok else '❌ FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--skip-hybrid", action="store_true")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()
    base = args.base_url
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    results = []

    print("=" * 70)
    print("A6 按需加载两阶段协议验收（LOAD_REFS / LOAD_SETTING）")
    print("=" * 70)

    h = unwrap(http(base, "GET", "/api/v1/health"))
    print(f"[S1] 后端 {h.get('status')} v{h.get('version')}")
    models = unwrap(http(base, "GET", "/api/v1/models"))
    if isinstance(models, dict):
        models = models.get("items", [])
    default = next((m for m in models if m.get("is_default")), None)
    print(f"     默认模型 = {default['name'] if default else '?'}")

    pid = None
    setting_id = None
    try:
        # ---- S2 作品 ----
        proj = unwrap(http(base, "POST", "/api/v1/projects", {
            "name": f"按需加载验证-{ts}", "genre": "玄幻修仙",
            "summary": "A6 两阶段按需加载验收作品，测完即删。"}))
        pid = proj["id"]
        print(f"[S2] 作品 {pid[:8]}…")

        # ---- S3 设定库（不可猜数值）+ 绑定到作品 ----
        st = unwrap(http(base, "POST", "/api/v1/settings", {
            "name": SETTING_NAME, "category": "经济",
            "levels": ["下品灵石", "中品灵石", "上品灵石"],
            "description": SETTING_DESC, "tags": ["货币", "灵石", "兑率"]}))
        setting_id = st["id"]
        http(base, "PUT", f"/api/v1/projects/{pid}/settings", {"setting_ids": [setting_id]})
        bound = unwrap(http(base, "GET", f"/api/v1/projects/{pid}/settings"))
        print(f"[S3] 设定「{SETTING_NAME}」已建并绑定（settings={bound.get('setting_ids')}）")

        # ---- S4 参考文档（不可猜名字）----
        ref = unwrap(http(base, "POST", f"/api/v1/projects/{pid}/references", {
            "filename": REF_FILENAME, "content_text": REF_CONTENT,
            "content_type": "text/plain"}))
        print(f"[S4] 参考文档「{REF_FILENAME}」已建（id={ref['id'][:8]}…）")

        # ---- S5 商讨：两阶段按需加载 ----
        print(f"\n[S5] 商讨（需同时加载参考 + 设定）...")
        t0 = time.time()
        events, refs, text, ctx = run_chat(base, pid, QUESTION, timeout=args.timeout)
        dt = time.time() - t0
        print(f"     耗时 {dt:.0f}s | 事件序列: {' → '.join(events)}")
        print(f"     refs 事件 : {json.dumps(refs, ensure_ascii=False) if refs else '(无)'}")
        print(f"     正文前 200 字: {text[:200].strip()}")

        print("\n   —— 断言 ——")
        results.append(verdict("收到 refs 事件（两阶段协议被触发）", refs is not None))
        loaded = (refs or {}).get("loaded") or []
        results.append(verdict(
            "加载了参考文档", REF_FILENAME in loaded, f"loaded={loaded}"))
        results.append(verdict(
            "加载了设定库详情", SETTING_NAME in loaded, f"loaded={loaded}"))
        has_stele = STELE_ANSWER in text
        has_stone = SPIRIT_STONE_ANSWER in text
        results.append(verdict(
            f"答对剑碑名（{STELE_ANSWER}）→ 参考正文确已注入", has_stele))
        results.append(verdict(
            f"答对灵石兑率（{SPIRIT_STONE_ANSWER}）→ 设定详情确已注入", has_stone))
        results.append(verdict(
            "正文未泄漏协议标记 LOAD_REFS/LOAD_SETTING",
            not re.search(r"LOAD_(REFS|SETTING)", text)))

        # ---- S6 商讨：无需资料的短路路径 ----
        print(f"\n[S6] 商讨（常识问题，应短路不加载）...")
        events2, refs2, text2, _ = run_chat(base, pid, COMMON_QUESTION, timeout=args.timeout)
        print(f"     事件序列: {' → '.join(events2)}")
        print(f"     正文前 120 字: {text2[:120].strip()}")
        print("\n   —— 断言 ——")
        results.append(verdict("常识问题未触发 refs 事件（短路生效）", refs2 is None,
                               f"refs={refs2}"))
        results.append(verdict("常识问题有正常回复", len(text2.strip()) > 10))

        # ---- S7 章节 hybrid 路径 ----
        if not args.skip_hybrid:
            print(f"\n[S7] 章节生成 hybrid 按需 top-up ...")
            vol = unwrap(http(base, "POST", f"/api/v1/projects/{pid}/volumes",
                              {"name": "第一卷", "summary": "A6"}))
            art = unwrap(http(base, "POST", f"/api/v1/projects/{pid}/volumes/{vol['id']}/articles",
                              {"name": "第一篇", "volume_id": vol["id"], "summary": "A6"}))
            ch = unwrap(http(base, "POST", f"/api/v1/articles/{art['id']}/chapters",
                             {"chapter_no": 1, "title": "第1章 剑碑林", "article_id": art["id"]}))
            gen_body = {
                "chapter_no": 1, "title": "第1章 剑碑林",
                "article_id": art["id"], "chapter_id": ch["id"],
                # hybrid top-up 的触发条件是「全局池文档的标签/文件名真实命中要点」
                # （score_reference>=4，见 chapter.py:_global_topup_ids）——
                # 故要点必须自然包含一个全局资料标签（这里用「地名」，命中「地名·*」系列）。
                "prompt_hint": "沈砚翻出宗门地名图册，在太虚剑宗山门剑碑林前驻足，辨认第七柄剑碑的刻字。",
                "word_range": {"min": 600, "max": 1000},
                "temperature": 0.4, "from_discussion": False,
            }
            if default:
                gen_body["model_id"] = default["id"]
            ctx_meta, events3 = None, []
            resp = http(base, "POST", f"/api/v1/projects/{pid}/chapters/generate",
                        body=gen_body, timeout=args.timeout, stream=True)
            try:
                for ev, payload in read_sse(resp):
                    if ev != "chunk":
                        events3.append(ev)
                    if ev == "context":
                        ctx_meta = payload
                    elif ev == "done":
                        break
            finally:
                resp.close()
            mode = (ctx_meta or {}).get("ref_mode")
            extra = (ctx_meta or {}).get("refs_loaded_extra") or []
            print(f"     事件序列: {' → '.join(events3)}")
            print(f"     ref_mode={mode} | refs_loaded_extra={extra}")
            print("\n   —— 断言 ——")
            if mode == "hybrid":
                results.append(verdict("hybrid 模式生效且按需补入了资料", bool(extra),
                                       f"extra={extra}"))
            else:
                print("   ⏭️  SKIP  后端未以 NA_CHAPTER_REF_MODE=hybrid 启动"
                      "（属预期，默认 pick_relevant 模式不走上限）")

        # ---- 汇总 ----
        print("\n" + "=" * 70)
        ok = sum(1 for r in results if r)
        print(f"汇总：{ok}/{len(results)} 项通过")
        print("=" * 70)

    finally:
        if pid and not args.keep:
            try:
                http(base, "DELETE", f"/api/v1/projects/{pid}")
                print(f"[S9] 已清理作品 {pid[:8]}…")
            except Exception as e:
                print(f"[S9] 清理失败: {e}")
        if setting_id:
            try:
                http(base, "DELETE", f"/api/v1/settings/{setting_id}")
                print(f"     已清理设定 {setting_id[:8]}…")
            except Exception:
                pass


if __name__ == "__main__":
    main()
