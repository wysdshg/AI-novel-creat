"""一键端到端全链路测试：建作品 → 卷 → 篇 → 章 → 真实生成一章（默认 2500 字）→ 质量评估 → 清理。

用途：生成逻辑每次改动（向量检索 / GraphRAG / 混合检索 / prompt 调整 / 解码参数）
之后，跑本脚本得到一份可对比的标准质量报告。

前置：后端已启动（默认 http://127.0.0.1:8000），且「模型配置」里有可用的默认模型。

运行（必须在 backend/ 下执行）：
  cd E:/AI小说创作/backend
  E:/AI小说创作/.venv/Scripts/python.exe tests/e2e/test_full_chain.py

可选参数：
  --base-url http://127.0.0.1:8000   后端地址
  --target-words 2500                目标字数（传给 word_range.min/max ±300）
  --model <model_id>                 指定模型（默认用系统的 is_default 模型）
  --keep                             保留测试作品不删（调试用）
  --timeout 600                      SSE 读超时（秒）

质量指标阈值依据 docs/04-踩坑档案.md B1（ModelScope Qwen3.5 长生成退化特征）：
  标点密度 / 最长无标点段 / 拉丁字母数 / 3-gram 重复率 / 错误标记。
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

# 本机请求必须绕过系统代理（Clash 等）：代理劫持 127.0.0.1 会返回 502 假象，
# 与 curl --noproxy '*' 同理（2026-09-10 实测踩中）。
urllib.request.install_opener(
    urllib.request.build_opener(urllib.request.ProxyHandler({})))

PUNCT = set("，。！？；：、""''…—（）《》【】,.!?;:\"'()")
ERROR_MARKERS = ("[模型调用失败", "未配置可用模型", "[生成中断")

TH = {
    "min_chars": 1800,        # 目标 2500，容差下限
    "punct_lo": 0.08,         # 标点密度下限（退化时骤降）
    "punct_hi": 0.35,         # 上限（碎句化）
    "max_no_punct": 60,       # 最长无标点段（退化时 >100）
    "max_latin": 20,          # 拉丁字母数（人名退化拼音/夹英文）
    "gram_warn": 15,          # 同一 3-gram 重复：>15 风格单调警示
    "gram_fail": 40,          # >40 才算复读机级故障（真循环会数百次）
    "humanize_pass": 60,      # 去AI味分数及格线
    "humanize_fail": 40,      # 低于此直接 FAIL
}


def http(base, method, path, body=None, timeout=30, stream=False):
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
    """逐行解析 SSE，yield (event, data_dict)。"""
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


def quality_metrics(text):
    chars = [c for c in text if not c.isspace()]
    n = len(chars)
    punct_n = sum(1 for c in chars if c in PUNCT)
    density = punct_n / n if n else 0.0
    # 最长无标点段
    longest, cur = 0, 0
    for c in chars:
        if c in PUNCT:
            longest = max(longest, cur)
            cur = 0
        else:
            cur += 1
    longest = max(longest, cur)
    # 拉丁字母
    latin = sum(1 for c in chars if c.isascii() and c.isalpha())
    # 3-gram 重复（保留原始空白：段落/句子边界不跨，段首主语重复不计入）
    grams = Counter(text[i:i + 3] for i in range(len(text) - 2))
    grams = Counter({g: n for g, n in grams.items() if not any(c.isspace() for c in g)})
    top3 = grams.most_common(5)
    max_repeat = top3[0][1] if top3 else 0
    # 段首词重复（风格单调度，信息性指标，不判 FAIL）
    paras = [p.strip() for p in re.split(r"\n+", text) if len(p.strip()) >= 10]
    head_counts = Counter(p[:2] for p in paras)
    head_top = head_counts.most_common(3)
    markers = [m for m in ERROR_MARKERS if m in text]
    return {
        "chars": n, "punct_density": round(density, 3),
        "max_no_punct_len": longest, "latin_count": latin,
        "max_3gram_repeat": max_repeat, "top_3gram": top3,
        "para_head_repeat": head_top,
        "error_markers": markers,
    }


def judge(m, humanize_score, repetition_stopped):
    checks, fails, warns = [], [], []

    def ck(name, ok, detail, level="fail"):
        checks.append((name, ok, detail, level))
        if not ok:
            (fails if level == "fail" else warns).append(f"{name}（{detail}）")

    ck("字数达标", m["chars"] >= TH["min_chars"], f"{m['chars']} 字，阈值 ≥{TH['min_chars']}")
    ck("标点密度正常", TH["punct_lo"] <= m["punct_density"] <= TH["punct_hi"],
       f"{m['punct_density']}，正常区间 [{TH['punct_lo']},{TH['punct_hi']}]")
    ck("最长无标点段", m["max_no_punct_len"] <= TH["max_no_punct"],
       f"{m['max_no_punct_len']} 字，阈值 ≤{TH['max_no_punct']}（退化征兆则 >100）")
    ck("无拉丁退化", m["latin_count"] <= TH["max_latin"],
       f"{m['latin_count']} 个，阈值 ≤{TH['max_latin']}")
    ck("无复读机循环", not repetition_stopped,
       "后端循环检测未触发" if not repetition_stopped else f"后端检测到重复并截断: {repetition_stopped}")
    ck("句式复用可控", m["max_3gram_repeat"] <= TH["gram_fail"],
       f"3-gram 最大重复 {m['max_3gram_repeat']} 次（>{TH['gram_fail']} 才算复读机故障）",
       level="fail" if m["max_3gram_repeat"] > TH["gram_fail"] else "warn")
    ck("无错误标记", not m["error_markers"], str(m["error_markers"]) or "干净")
    if humanize_score is not None:
        ck("去AI味分数", humanize_score >= TH["humanize_fail"],
           f"{humanize_score}（及格 {TH['humanize_pass']}，FAIL 线 {TH['humanize_fail']}）")
    return checks, fails, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--target-words", type=int, default=2500)
    ap.add_argument("--model", default=None, help="model_id，默认用系统默认模型")
    ap.add_argument("--thinking", default=None, choices=["on", "off"],
                    help="显式指定 enable_thinking（默认不传=跟随后端策略）")
    ap.add_argument("--keep", action="store_true", help="保留测试作品不删")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    base, results, fails_all = args.base_url, [], []
    t0 = datetime.now()
    ts = t0.strftime("%Y%m%d-%H%M%S")
    print(f"=== E2E 全链路测试 {ts} ===")
    print(f"后端: {base}  目标字数: {args.target_words}\n")

    # ---- S0 健康检查 ----
    print("[S0] 健康检查 ...", end=" ")
    try:
        h = unwrap(http(base, "GET", "/api/v1/health"))
        print("OK", h)
    except Exception as e:
        print("FAIL:", e)
        print("后端未启动或地址不对，先启动：cd backend && .venv/Scripts/python.exe dev.py")
        return 1

    # ---- S1 默认模型 ----
    print("[S1] 模型配置 ...", end=" ")
    models = unwrap(http(base, "GET", "/api/v1/models")) or []
    default = next((m for m in models if m.get("is_default")), None)
    model_name = default["name"] if default else "?"
    model_id = args.model or (default["id"] if default else None)
    print(f"默认模型 = {model_name} ({model_id})")

    # ---- S2~S5 建结构 ----
    print("[S2] 创建作品 ...", end=" ")
    proj = unwrap(http(base, "POST", "/api/v1/projects", {
        "name": f"E2E-{ts}", "genre": "测试题材",
        "summary": "端到端链路测试作品，测完即删。"}))
    pid = proj["id"]
    print("OK", pid[:8] + "…")

    print("[S3] 创建卷 ...", end=" ")
    vol = unwrap(http(base, "POST", f"/api/v1/projects/{pid}/volumes",
                      {"name": "测试卷", "summary": "E2E"}))
    vid = vol["id"]
    print("OK")

    print("[S4] 创建篇 ...", end=" ")
    art = unwrap(http(base, "POST", f"/api/v1/projects/{pid}/volumes/{vid}/articles",
                      {"name": "测试篇", "volume_id": vid, "summary": "E2E"}))
    aid = art["id"]
    print("OK")

    print("[S5] 创建章 ...", end=" ")
    ch = unwrap(http(base, "POST", f"/api/v1/articles/{aid}/chapters",
                     {"chapter_no": 1, "title": "第1章 城隍庙的铜牌", "article_id": aid}))
    cid = ch["id"]
    print("OK", cid[:8] + "…")

    # ---- S6 生成（SSE） ----
    print(f"\n[S6] 生成第 1 章（目标 {args.target_words} 字）...")
    gen_body = {
        "chapter_no": 1, "title": "第1章 城隍庙的铜牌",
        "article_id": aid, "chapter_id": cid,
        "prompt_hint": "主角沈砚在大雨夜躲进城隍庙，遇到一个浑身湿透的孩子，"
                       "孩子递来一枚刻着奇怪符号的铜牌后消失。",
        "word_range": {"min": args.target_words - 300, "max": args.target_words + 300},
        "temperature": 0.4, "from_discussion": False,
    }
    if model_id:
        gen_body["model_id"] = model_id
    if args.thinking == "on":
        gen_body["enable_thinking"] = True
    elif args.thinking == "off":
        gen_body["enable_thinking"] = False

    text_parts, events_seen = [], []
    ttfc, saved_info, validate_info, stopped = None, None, None, None
    gen_start = time.time()
    resp = http(base, "POST", f"/api/v1/projects/{pid}/chapters/generate",
                body=gen_body, timeout=args.timeout, stream=True)
    try:
        for ev, payload in read_sse(resp):
            if ev not in ("chunk",):
                events_seen.append(ev)
            if ev == "chunk":
                if ttfc is None:
                    ttfc = time.time() - gen_start
                t = payload.get("text", "")
                text_parts.append(t)
                sys.stdout.write(".")
                sys.stdout.flush()
            elif ev == "stopped":
                stopped = payload
            elif ev == "validate":
                validate_info = payload
            elif ev == "saved":
                saved_info = payload
            elif ev == "done":
                break
    finally:
        resp.close()
    gen_secs = time.time() - gen_start
    streamed = "".join(text_parts)
    print(f"\n  事件序列: {' → '.join(events_seen)}")
    print(f"  耗时 {gen_secs:.1f}s | 首字 {ttfc:.1f}s" if ttfc else f"\n  耗时 {gen_secs:.1f}s | 无 chunk！")

    # ---- S7 落库正文 ----
    print("[S7] 拉回落库正文 ...", end=" ")
    saved_ch = unwrap(http(base, "GET", f"/api/v1/projects/{pid}/chapters/{cid}"))
    db_text = saved_ch.get("content", "")
    print(f"DB {len(db_text)} 字 / 流式 {len(streamed)} 字")

    final_text = db_text or streamed

    # ---- S8 质量指标 ----
    print("[S8] 质量指标：")
    m = quality_metrics(final_text)
    print(f"  字数          : {m['chars']}")
    print(f"  生成速度      : {m['chars'] / gen_secs:.0f} 字/秒")
    print(f"  标点密度      : {m['punct_density']}（正常 0.13~0.20）")
    print(f"  最长无标点段  : {m['max_no_punct_len']} 字（>100 = 退化）")
    print(f"  拉丁字母      : {m['latin_count']} 个（人名退化拼音会飙高）")
    print(f"  3-gram 最大重复: {m['max_3gram_repeat']} 次  top: {m['top_3gram'][:3]}")
    print(f"  段首开头 top   : {m['para_head_repeat']}（风格单调度，仅参考）")
    print(f"  错误标记      : {m['error_markers'] or '无'}")
    if stopped:
        print(f"  ⚠️ 触发重复中断: {stopped}")
    if validate_info is not None:
        issues = validate_info.get("issues", [])
        print(f"  设定校验 issues: {len(issues)}（注意：/validate 曾实测为假绿灯，仅记录）")

    # ---- S8b 去AI味 ----
    humanize_score = None
    try:
        hum = unwrap(http(base, "POST", "/api/v1/humanize/scan",
                          {"text": final_text[:4000], "scene": "chapter"}))
        humanize_score = hum.get("score")
        print(f"  去AI味分数    : {humanize_score}（issues {hum.get('issue_count', '?')}）")
    except Exception as e:
        print(f"  去AI味扫描跳过（{e}）")

    checks, fails, warns = judge(m, humanize_score, stopped is not None)
    print("  --- 判定 ---")
    for name, ok, detail, level in checks:
        mark = "✅" if ok else ("⚠️" if level == "warn" else "❌")
        print(f"  {mark} {name}: {detail}")
    if not saved_info:
        fails_all.append("SSE 未收到 saved 事件")
    if ttfc is None:
        fails_all.append("SSE 未收到任何 chunk")
    fails_all.extend(fails)
    warn_all = warns

    # ---- S9 写后摄取 ----
    print("[S9] 等待写后摄取（异步）...", end=" ")
    mem_ok = False
    for _ in range(30):
        time.sleep(2)
        mems = unwrap(http(base, "GET", f"/api/v1/projects/{pid}/memory/chapters"))
        s = json.dumps(mems, ensure_ascii=False)
        if cid in s or '"chapter_no": 1' in s or '"chapter_no":1' in s:
            mem_ok = True
            break
    print("OK（章级记忆已生成）" if mem_ok else "超时未看到章级记忆（摄取可能失败）")
    if not mem_ok:
        fails_all.append("写后摄取 60s 内未产生章级记忆")

    # ---- S10 清理 ----
    if args.keep:
        print(f"[S10] --keep 保留测试作品 {pid}")
    else:
        print("[S10] 清理测试作品 ...", end=" ")
        http(base, "DELETE", f"/api/v1/projects/{pid}")
        try:
            http(base, "GET", f"/api/v1/projects/{pid}")
            print("⚠️ 删除后仍可 GET（级联异常！）")
            fails_all.append("删除作品后仍能查到（级联删除异常）")
        except urllib.error.HTTPError as e:
            print(f"OK（GET 复核 {e.code}，级联干净）")

    # ---- 汇总 ----
    print("\n" + "=" * 60)
    if fails_all:
        print(f"❌ 未通过 {len(fails_all)} 项：")
        for f in fails_all:
            print("  -", f)
    else:
        print("✅ 全链路测试通过")
    for w in warn_all:
        print("  ⚠️ 警示:", w)

    # ---- 报告落盘 ----
    rpt_dir = Path(__file__).resolve().parents[1] / "reports"
    rpt_dir.mkdir(exist_ok=True)
    report = {
        "time": t0.isoformat(), "model": model_name, "model_id": model_id,
        "target_words": args.target_words, "gen_secs": round(gen_secs, 1),
        "ttfc": round(ttfc, 1) if ttfc else None,
        "metrics": m, "humanize_score": humanize_score,
        "events": events_seen, "stopped": stopped,
        "saved": saved_info, "memory_ok": mem_ok,
        "passed": not fails_all, "fails": fails_all, "warns": warn_all,
    }
    (rpt_dir / f"report-{ts}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (rpt_dir / f"chapter-{ts}.txt").write_text(final_text, encoding="utf-8")
    if streamed != final_text:
        (rpt_dir / f"chapter-stream-{ts}.txt").write_text(streamed, encoding="utf-8")
        print(f"  ⚠️ 流式与落库不一致，已存流式原文: chapter-stream-{ts}.txt")
    print(f"\n报告与正文已存: tests/reports/report-{ts}.json / chapter-{ts}.txt")
    return 1 if fails_all else 0


if __name__ == "__main__":
    sys.exit(main())
