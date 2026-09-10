"""A 线检索链路端到端验证（A5 验收）：造实体图 → 真实生成 → 看「AI 这次到底读了什么」。

与 test_full_chain.py 的分工：
- test_full_chain.py = **生成质量基线**（字数/标点/去AI味/复读），不关心检索；
- 本脚本 = **检索注入验收**：验证 GraphRAG 一跳扩展、关键词/向量/RRF/rerank 四段
  是否真的把该给的资料给了模型。

关键设计：prompt_hint 里**只点一个名字**（沈砚），其余实体（师父/道侣/宗门/关联地点）
必须靠实体图一跳带出来。若扩展失效，context 事件的 entity_graph.added 会是空。

前置：后端已启动，且 A3/A4/A5 代码已加载（改过后端需重启）。

运行：
  cd E:/AI小说创作/backend
  E:/AI小说创作/.venv/Scripts/python.exe tests/e2e/test_retrieval_chain.py

可选参数：
  --base-url http://127.0.0.1:8000
  --keep          保留测试作品（调试）
  --no-generate   只造数据 + 验证 context 注入，不真跑生成（省时省 API）
"""
import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime

urllib.request.install_opener(
    urllib.request.build_opener(urllib.request.ProxyHandler({})))


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


def seed_graph(base, pid):
    """造一张最小但真实感的实体图。

    沈砚(主角) —师徒→ 玄真子(掌门) ；沈砚 —道侣→ 苏清月 ；玄真子 —宿敌→ 陆离
    太虚剑宗(members 含沈砚/玄真子, leader=玄真子) ；幽冥殿(members 含陆离)
    地点：城隍庙(related=沈砚) / 太虚剑宗山门(related=太虚剑宗)
    """
    C = lambda **kw: unwrap(http(base, "POST", f"/api/v1/projects/{pid}/characters", kw))

    shen = C(name="沈砚", role_type="主角", gender="男", current_level="炼气七层",
             personality="外冷内热，遇事先算后动，护短",
             background="城隍庙雨夜拾得铜牌的弃子",
             brief="主角。铜牌持有者，剑道天赋异常。")
    xuan = C(name="玄真子", role_type="配角", gender="男", current_level="筑基后期",
             personality="严苛寡言，护犊子", background="太虚剑宗当代掌门",
             brief="沈砚的师父，太虚剑宗掌门。")
    su = C(name="苏清月", role_type="配角", gender="女", current_level="炼气九层",
           personality="机敏爱笑，擅长阵法", background="药王谷旁支",
           brief="沈砚的道侣，阵法天才。")
    lu = C(name="陆离", role_type="反派", gender="男", current_level="筑基大圆满",
           personality="阴柔狠戾", background="幽冥殿少主",
           brief="幽冥殿少主，与太虚剑宗世代宿怨。")

    F = lambda **kw: unwrap(http(base, "POST", f"/api/v1/projects/{pid}/factions", kw))
    ty = F(name="太虚剑宗", description="正道六大宗之一，以剑入道，山门在太虚峰。",
           leader_id=xuan["id"], members=["沈砚", xuan["id"]], territory="太虚峰",
           status="active")
    ym = F(name="幽冥殿", description="魔道势力，行事诡秘，擅长养魂。",
           leader_id=lu["id"], members=[lu["id"]], territory="幽冥谷",
           status="active")

    R = lambda **kw: unwrap(http(base, "POST", f"/api/v1/projects/{pid}/relations", kw))
    R(subject_id=shen["id"], object_id=xuan["id"], relation_type="师徒", strength=90,
      note="玄真子亲传，倾囊相授")
    R(subject_id=shen["id"], object_id=su["id"], relation_type="道侣", strength=85,
      note="约定结丹后双修")
    R(subject_id=xuan["id"], object_id=lu["id"], relation_type="宿敌", strength=70,
      note="二十年前幽冥谷一役结仇")

    L = lambda **kw: unwrap(http(base, "POST", f"/api/v1/projects/{pid}/locations", kw))
    L(name="城隍庙", location_type="建筑", region="临江城",
      description="临江城西一座荒废庙宇，雨夜常有人避雨。",
      notable_features=["断裂的铜钟", "褪色城隍像"], related_ids=[shen["id"]])
    L(name="太虚剑宗山门", location_type="门派", region="太虚峰",
      description="千级石阶直上云海，两侧立七十二柄剑碑。",
      notable_features=["剑碑林", "问心阶"], related_ids=[ty["id"]])

    return {"shen": shen, "xuan": xuan, "su": su, "lu": lu, "ty": ty, "ym": ym}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--no-generate", action="store_true")
    ap.add_argument("--target-words", type=int, default=1500)
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()
    base = args.base_url
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    print("=" * 68)
    print("A 线检索链路端到端验证")
    print("=" * 68)

    # ---- S1 健康 ----
    h = unwrap(http(base, "GET", "/api/v1/health"))
    print(f"[S1] 后端 {h.get('status')} v{h.get('version')}")
    models = unwrap(http(base, "GET", "/api/v1/models"))
    if isinstance(models, dict):
        models = models.get("items", [])
    default = next((m for m in models if m.get("is_default")), None)
    print(f"     默认模型 = {default['name'] if default else '?'}")

    pid = None
    try:
        # ---- S2 作品 ----
        proj = unwrap(http(base, "POST", "/api/v1/projects", {
            "name": f"检索验证-{ts}", "genre": "玄幻修仙",
            "summary": "A5 检索链路验证用作品，测完即删。"}))
        pid = proj["id"]
        print(f"[S2] 作品 {pid[:8]}…")

        # ---- S3 实体图 ----
        g = seed_graph(base, pid)
        print("[S3] 实体图已建：4 角色 / 2 势力 / 2 地点 / 3 关系")

        # ---- S4 导入全局参考资料（给向量+rerank 通道候选）----
        pool = unwrap(http(base, "GET", "/api/v1/references/global")) or []
        pick = [d for d in pool if any(k in d["filename"] for k in
                ("势力名称·玄幻", "地名·修仙城市", "古代府县镇村", "取名素材·男尾"))][:4]
        n = 0
        if pick:
            res = unwrap(http(base, "POST", f"/api/v1/projects/{pid}/references/import-global",
                              {"doc_ids": [d["id"] for d in pick]}))
            n = res if isinstance(res, int) else (res.get("imported", len(pick)) if isinstance(res, dict) else len(pick))
        print(f"[S4] 导入全局参考 {n} 份（向量通道候选；无 key 时为 0 向量）")

        # ---- S5 结构 ----
        vol = unwrap(http(base, "POST", f"/api/v1/projects/{pid}/volumes",
                          {"name": "第一卷", "summary": "检索验证"}))
        art = unwrap(http(base, "POST", f"/api/v1/projects/{pid}/volumes/{vol['id']}/articles",
                          {"name": "第一篇", "volume_id": vol["id"], "summary": "检索验证"}))
        ch = unwrap(http(base, "POST", f"/api/v1/articles/{art['id']}/chapters",
                         {"chapter_no": 1, "title": "第1章 剑碑问心", "article_id": art["id"]}))
        print(f"[S5] 卷/篇/章已建 chapter_id={ch['id'][:8]}…")

        # ---- S6 生成（prompt_hint 只点主角名，其余靠实体图带出）----
        gen_body = {
            "chapter_no": 1, "title": "第1章 剑碑问心",
            "article_id": art["id"], "chapter_id": ch["id"],
            "prompt_hint": "沈砚回到山上，想请师父一同去追查铜牌的来历，"
                           "途中先遇到道侣，两人起了争执。",
            "word_range": {"min": args.target_words - 300, "max": args.target_words + 300},
            "temperature": 0.4, "from_discussion": False,
        }
        if default:
            gen_body["model_id"] = default["id"]

        text_parts, ctx_meta, events = [], None, []
        stopped = None
        for attempt in range(1, 4):
            text_parts, ctx_meta, events, stopped = [], None, [], None
            t0 = time.time()
            resp = http(base, "POST", f"/api/v1/projects/{pid}/chapters/generate",
                        body=gen_body, timeout=args.timeout, stream=True)
            try:
                for ev, payload in read_sse(resp):
                    if ev != "chunk":
                        events.append(ev)
                    if ev == "chunk":
                        text_parts.append(payload.get("text", ""))
                    elif ev == "context":
                        ctx_meta = payload
                    elif ev == "stopped":
                        stopped = payload
                    elif ev == "done":
                        break
            finally:
                resp.close()
            print(f"[S6] 生成完成 {time.time()-t0:.0f}s / {sum(len(x) for x in text_parts)} 字"
                  + (f"（stopped={stopped.get('reason')}）" if stopped else ""))
            break

        # ---- S7 检索注入验收 ----
        print("\n" + "=" * 68)
        print("检索注入验收（AI 这次读到了什么）")
        print("=" * 68)
        if ctx_meta is None:
            print("❌ 未收到 context 事件")
        else:
            print(f"事件序列: {' → '.join(events)}")
            print(f"预算档位: {ctx_meta.get('budget', {}).get('level', '?')}")
            print("\n-- 实体图一跳扩展 (A5) --")
            eg = ctx_meta.get("entity_graph") or {}
            if eg.get("enabled") is False:
                print("  ⚠️ 扩展被关闭")
            seeds = (eg.get("seeds") or {})
            print(f"  种子: 角色{seeds.get('characters')} 势力{seeds.get('factions')} "
                  f"地点{seeds.get('locations')}")
            added = eg.get("added") or {}
            if not any(added.values()):
                print("  ❌ 未扩展出任何邻居实体（GraphRAG 未生效？）")
            for kind, items in added.items():
                for it in items:
                    print(f"  + {kind}: {it}")
            print("\n-- 最终命中实体 --")
            m = ctx_meta.get("mentions") or {}
            for k in ("characters", "factions", "locations"):
                print(f"  {k}: {m.get(k)}")
            print("\n-- 参考资料命中明细 (A3+A4) --")
            for d in (ctx_meta.get("references") or []):
                print(f"  · {d.get('filename', '')[:22]:24s} rrf={d.get('score')} "
                      f"kw={d.get('kw_score')} vec={d.get('vec_score')} "
                      f"rerank={d.get('rerank_score')} {d.get('channels')}")
            if not ctx_meta.get("references"):
                print("  （无参考命中）")

        # ---- S8 正文摘要 ----
        text = "".join(text_parts)
        if text:
            print("\n-- 正文开头 240 字 --")
            print(text[:240].replace("\n", " "))
            # 关键：检查扩展进来的实体是否真的出现在正文（说明模型用上了）
            print("\n-- 扩展实体在正文中的出现次数 --")
            for name in ("玄真子", "苏清月", "陆离", "太虚剑宗", "幽冥殿", "城隍庙"):
                print(f"  {name}: {text.count(name)} 次")

        # ---- S9 清理 ----
        if not args.keep:
            http(base, "DELETE", f"/api/v1/projects/{pid}")
            print(f"\n[S9] 已清理作品 {pid[:8]}…")
        else:
            print(f"\n[S9] --keep，保留作品 {pid}")
    except Exception as e:
        print(f"\n❌ 失败: {type(e).__name__}: {e}")
        if pid and not args.keep:
            try:
                http(base, "DELETE", f"/api/v1/projects/{pid}")
                print(f"已清理作品 {pid[:8]}…")
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
