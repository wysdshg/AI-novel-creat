"""端到端探针：上下文引擎 + 写后摄取 + 记忆 + 去AI味 + SKILL 调度。

用临时 SQLite 库跑，不碰用户真实数据。注册一个假模型适配器，
让摄取链路在不依赖 Ollama 的情况下也能验证。

运行（必须在 backend/ 下执行）：
  cd E:/AI小说创作/backend
  E:/AI小说创作/.venv/Scripts/python.exe tests/e2e/probe_pipeline.py
"""
import json
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

# ---- 临时库，隔离真实数据 ----
tmp = Path(tempfile.gettempdir()) / f"probe_{uuid.uuid4().hex[:8]}.db"
import app.core.database as dbmod  # noqa: E402
dbmod.DEFAULT_DB_URL = f"sqlite:///{tmp}"

from app.core.database import init_db  # noqa: E402
from app.core.gateway.base import BaseModelAdapter  # noqa: E402
from app.core.gateway.registry import register  # noqa: E402

FAKE_EXTRACT = {
    "summary": "陈砚在青云宗试炼场遭到赵烈挑衅，被迫接下三招之约。他以残缺的《碎星诀》勉强撑过两招，第三招时体内灵脉崩裂，却在昏迷前看见玉牌上浮现出一行陌生刻字。",
    "ending_hook": "玉牌上的刻字是谁留下的，陈砚昏迷前只看清了半个字。",
    "characters": ["陈砚", "赵烈"],
    "locations": ["青云宗"],
    "plot_points": ["赵烈当众挑衅陈砚", "陈砚接下三招之约", "灵脉崩裂昏迷", "玉牌浮现刻字"],
    "foreshadow_actions": [{"action": "bury", "desc": "玉牌上的陌生刻字"}],
    "new_entities": [{"kind": "location", "name": "试炼场", "brief": "青云宗弟子比试之地"}],
    "next_directions": [
        {"title": "追查刻字来历", "detail": "陈砚醒来后拿玉牌去藏经阁比对古文字，牵出一段被抹去的宗门旧事。", "tension": "中"},
        {"title": "赵烈的后手", "detail": "赵烈发现陈砚没死，开始暗中调查他的功法来源。", "tension": "高"},
        {"title": "灵脉崩裂的代价", "detail": "陈砚修为跌落，被迫从杂役做起，反而接触到宗门底层的秘密。", "tension": "低"},
    ],
}


@register("fake")
class FakeAdapter(BaseModelAdapter):
    def chat(self, messages, **params) -> str:
        sys_text = messages[0]["content"] if messages else ""
        if "阶段脉络" in sys_text:
            return json.dumps({"summary": "第一阶段主线：陈砚从被欺压到握有玉牌线索。",
                               "key_events": ["三招之约"], "open_threads": ["玉牌刻字"]},
                              ensure_ascii=False)
        # 故意包一层代码块 + 加句废话，验证 JSON 容错
        return "好的，结果如下：\n```json\n" + json.dumps(FAKE_EXTRACT, ensure_ascii=False) + "\n```"

    async def astream(self, messages, **params):
        yield self.chat(messages)

    def stream(self, messages, **params):
        yield self.chat(messages)

    def test_connection(self) -> bool:
        return True


def main():
    init_db()
    db = dbmod.SessionLocal()

    from app.models.orm import ModelConfigORM
    from app.schemas.chapter import ChapterCreate
    from app.schemas.database import CharacterCreate, FactionCreate, LocationCreate
    
    from app.schemas.volume import VolumeCreate
    from app.schemas.article import ArticleCreate
    from app.services import (
        app_config, article_crud, chapter_crud, character_crud, discussion_crud,
        faction_crud, humanizer, ingestion, location_crud, memory_crud,
        project_crud, reference_crud, seed_skills, skill_dispatch, volume_crud,
    )
    from app.core.context import build_chapter_messages, build_discussion_system

    passed, failed = [], []

    def check(name, cond, extra=""):
        (passed if cond else failed).append(name)
        print(f"{'  [OK]' if cond else '  [FAIL]'} {name}{(' — ' + extra) if extra else ''}")

    # ---------- 准备数据 ----------
    print("\n=== 0. 准备测试数据 ===")
    seed_skills.install(db)
    proj = project_crud.create_project(db, {"name": "碎星纪", "genre": "东方玄幻",
                                            "summary": "少年陈砚以残诀逆袭的故事"})
    pid = proj["id"] if isinstance(proj, dict) else proj.id
    proj_name = proj["name"] if isinstance(proj, dict) else proj.name
    vol = volume_crud.create_volume(db, pid, VolumeCreate(name="第一卷 青云", summary="宗门试炼篇"))
    art = article_crud.create_article(db, pid, ArticleCreate(volume_id=vol.id, name="试炼篇",
                                                             summary="陈砚在青云宗立足"))
    aid = art.id

    character_crud.create_character(db, pid, CharacterCreate(
        name="陈砚", role_type="主角", gender="男", age=17, current_level="炼气三层",
        personality="沉默寡言，认死理", background="散修之子，父母失踪", talent="残缺的碎星诀"))
    character_crud.create_character(db, pid, CharacterCreate(
        name="赵烈", role_type="反派", gender="男", current_level="炼气七层",
        personality="骄横", brief="内门弟子，视陈砚为眼中钉"))
    character_crud.create_character(db, pid, CharacterCreate(
        name="林素", role_type="配角", gender="女", brief="药堂弟子"))
    faction_crud.create_faction(db, pid, FactionCreate(name="青云宗", description="东域三大宗之一",
                                                       territory="青云山"))
    location_crud.create_location(db, pid, LocationCreate(name="青云宗", description="山门所在"))
    discussion_crud.add_message(db, pid, "user", "下一章我想让陈砚和赵烈起冲突，但别直接打死")
    print(f"  作品={proj_name} 篇={art.name}")

    # ---------- 1. 上下文引擎 ----------
    print("\n=== 1. 上下文引擎（章节生成） ===")
    messages, meta = build_chapter_messages(
        db, pid, chapter_no=1, article_id=aid, volume_id=vol.id,
        prompt_hint="陈砚在试炼场被赵烈挑衅", from_discussion=True)
    sys_text, user_text = messages[0]["content"], messages[1]["content"]

    check("系统提示词含 SKILL 注入", "写作技能" in sys_text or "###" in sys_text)
    check("系统提示词含去AI味约束", "禁" in sys_text and ("眼中闪过" in sys_text or "不是" in sys_text))
    check("用户消息含角色卡", "陈砚" in user_text and "炼气三层" in user_text)
    check("命中角色全量注入", "碎星诀" in user_text)
    check("未命中角色只有一行", "药堂弟子" in user_text and user_text.count("林素") <= 2)
    check("含世界观", "碎星纪" in user_text and "东方玄幻" in user_text)
    check("含商讨记录", "别直接打死" in user_text)
    check("本章任务在最后", user_text.rstrip().endswith("注水。") or "【本章任务】" in user_text[-600:])
    check("实体识别命中", "陈砚" in meta["mentions"]["characters"] and "赵烈" in meta["mentions"]["characters"],
          str(meta["mentions"]))
    print(f"  上下文规模: system={meta['system_chars']} user={meta['user_chars']} "
          f"预算占用={meta['budget']['usage_pct']}%")

    # ---------- 2. 预算裁剪 ----------
    print("\n=== 2. 预算裁剪（tight 档） ===")
    _, meta_t = build_chapter_messages(db, pid, chapter_no=1, article_id=aid,
                                       prompt_hint="test", budget_level="tight")
    check("tight 档预算更小", meta_t["budget"]["budget"] == 8000)
    check("本章任务永不丢弃",
          any(k["key"] == "task" for k in meta_t["budget"]["kept"]))

    # ---------- 3. 写后摄取 ----------
    print("\n=== 3. 写后摄取（记忆 + 摘要 + 走向） ===")
    db.add(ModelConfigORM(id=uuid.uuid4().hex, name="fake", vendor="fake",
                          api_base="http://x", model_name="fake", is_default=True,
                          status="active", role="primary"))
    db.commit()

    body = ("试炼场上人声鼎沸。\n赵烈把剑往地上一插，说三招。\n"
            "陈砚没说话，只是把袖子挽了起来。\n" * 6)
    ch1 = chapter_crud.create_chapter(db, pid, ChapterCreate(
        chapter_no=1, title="第1章 三招之约", content=body, word_count=len(body), article_id=aid))
    r1 = ingestion.ingest_chapter(db, pid, ch1)

    check("摄取未走兜底（模型 JSON 解析成功）", r1.get("fallback") is False, str(r1.get("fallback")))
    mem = memory_crud.get_chapter_memory(db, pid, ch1.id)
    check("章级记忆已落库", mem is not None and len(mem.summary) > 50)
    check("关键事件已抽取", mem is not None and len(mem.plot_points) >= 3)
    check("结尾钩子已抽取", mem is not None and bool(mem.ending_hook))
    check("新实体待确认", mem is not None and mem.status == "pending" and len(mem.new_entities) == 1)

    corpus = reference_crud.get_references_corpus(db, pid, aid)
    check("篇章摘要已写入参考文档", "ch:1" in corpus or "第1章" in corpus, corpus[:60])

    msgs = discussion_crud.list_messages(db, pid)
    card = [m for m in msgs if (m.meta or {}).get("type") == "post_chapter_directions"]
    check("走向卡片已推送到对话区", len(card) == 1 and len(card[0].meta["directions"]) == 3)

    # ---------- 4. 追加式摘要不覆盖 ----------
    print("\n=== 4. 摘要追加不覆盖（原 bug 回归） ===")
    ch2 = chapter_crud.create_chapter(db, pid, ChapterCreate(
        chapter_no=2, title="第2章 醒来", content=body, word_count=len(body), article_id=aid))
    ingestion.ingest_chapter(db, pid, ch2)
    corpus2 = reference_crud.get_references_corpus(db, pid, aid)
    check("第1章摘要仍在", "ch:1" in corpus2)
    check("第2章摘要已追加", "ch:2" in corpus2)

    # 重生成第 2 章，应替换而不是再追加一段
    ingestion.ingest_chapter(db, pid, ch2)
    corpus3 = reference_crud.get_references_corpus(db, pid, aid)
    check("重复摄取不产生重复段", corpus3.count("<!-- ch:2 -->") == 1,
          f"count={corpus3.count('<!-- ch:2 -->')}")

    # ---------- 5. 记忆注入下一章 ----------
    print("\n=== 5. 记忆回注（第3章能读到前两章） ===")
    m3, meta3 = build_chapter_messages(db, pid, chapter_no=3, article_id=aid,
                                       prompt_hint="陈砚醒来")
    u3 = m3[1]["content"]
    check("含最近章节回顾", "最近章节回顾" in u3 and "玉牌" in u3)
    check("含上一章结尾原文", "上一章结尾" in u3)
    check("含本篇剧情摘要", "本篇已写剧情摘要" in u3 or "参考资料" in u3)

    # ---------- 6. 阶段压缩 ----------
    print("\n=== 6. 阶段压缩 ===")
    app_config.set_value(db, app_config.KEY_STAGE_EVERY, 2)
    rng = memory_crud.find_uncompressed_range(db, pid, 2)
    check("识别出可压缩区间", rng == (1, 2), str(rng))
    st = ingestion.compress_stage(db, pid, 1, 2)
    check("阶段摘要已生成", st is not None and len(st["summary"]) > 5)
    check("再次查找无可压缩区间", memory_crud.find_uncompressed_range(db, pid, 2) is None)

    # ---------- 7. 去 AI 味 ----------
    print("\n=== 7. 去AI味检测 ===")
    bad = ("他的眼中闪过一丝复杂的神色，仿佛看透了一切。这不是简单的挑衅，"
           "而是赤裸裸的羞辱。他知道，这一刻，他终于明白了什么叫做实力。"
           "空气仿佛凝固了一般，带着一丝不易察觉的压迫感。")
    good = ("赵烈把剑插进土里，剑柄还在晃。他说三招，接得住就算你赢。"
            "陈砚看了看那把剑，又看了看自己的手，慢慢把袖子挽上去。周围没人说话。")
    rb, rg = humanizer.scan(bad), humanizer.scan(good)
    check("AI味样本被判低分", rb["score"] < 40, f"score={rb['score']} issues={rb['issue_count']}")
    check("人写样本无误报", rg["score"] > 85, f"score={rg['score']} issues={rg['issue_count']}")

    # ---------- 8. SKILL 调度 ----------
    print("\n=== 8. SKILL 互斥调度 ===")
    ex = skill_dispatch.explain(db, "chapter")
    check("chapter 触发有生效 SKILL", len(ex["active"]) >= 3, f"active={len(ex['active'])}")
    cats = [a["category"] for a in ex["active"]]
    check("互斥类不重复", len([c for c in cats if c == "文风"]) <= 1, str(cats))
    check("禁忌类可叠加", cats.count("禁忌") >= 2, str(cats))
    prios = [a["priority"] for a in ex["active"]]
    check("按优先级升序（高优先级压轴）", prios == sorted(prios), str(prios))

    # ---------- 9. 商讨上下文 ----------
    print("\n=== 9. 商讨不再是瞎子 ===")
    dsys, dmeta = build_discussion_system(db, pid, chapter_no=3)
    check("商讨系统提示词含角色境界", "炼气三层" in dsys)
    check("商讨含记忆", "玉牌" in dsys or "前情脉络" in dsys)
    check("商讨注入 discussion 类 SKILL", "剧情商讨顾问" in dsys or "###" in dsys)
    print(f"  商讨上下文规模: {dmeta['system_chars']} 字符")

    # ---------- 10. 实体确认入库 ----------
    print("\n=== 10. 实体确认写库 ===")
    before = len(location_crud.list_locations(db, pid))
    from app.routers.assist import ConfirmEntitiesRequest, EntityItem, confirm_entities
    res = confirm_entities(pid, ConfirmEntitiesRequest(
        chapter_id=ch1.id,
        items=[EntityItem(kind="location", name="试炼场", brief="比试之地"),
               EntityItem(kind="location", name="青云宗", brief="重名应跳过")]), db)
    data = res["data"] if isinstance(res, dict) and "data" in res else res
    check("新地点已写库", len(location_crud.list_locations(db, pid)) == before + 1)
    check("重名被跳过", len(data["skipped"]) == 1, str(data["skipped"]))
    check("记忆状态转 confirmed",
          memory_crud.get_chapter_memory(db, pid, ch1.id).status == "confirmed")

    # ---------- 汇总 ----------
    print("\n" + "=" * 62)
    print(f"通过 {len(passed)} / {len(passed) + len(failed)}")
    if failed:
        print("失败项：")
        for f in failed:
            print("  -", f)
    db.close()
    try:
        tmp.unlink(missing_ok=True)
    except Exception:
        pass
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
