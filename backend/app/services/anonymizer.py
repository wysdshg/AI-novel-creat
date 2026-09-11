"""专名匿名化归一（Phase 7.1，2026-09-11 深夜，用户方案 + 三处修正）。

**动机**：用户实测发现计划生成照抄斗破开局（云岚宗/斗之气原名出现）——
根因是概括/模板里带着源书专名。本模块在**概括之后**追加匿名化归一：
入库即用代称，模板/计划/正文全链路天然无书味（反抄袭从"堵"变"无需"）。

流程（概括本身不动 —— 历史数据可直接补跑）：
  ① cast 抽取（LLM，分批）：主角 / 角色(敌友+功能) / 宗门家族势力地点物品 / 境界阶梯
  ② 代称分配（纯代码）：
     - 主角 → `主角`
     - 角色 → `友·配角1` / `敌·配角2`（数字无上限；敌友在前缀 —— 不用 A/a 大小写，
       LLM 高频笔误且视觉不可辨，一致性检查器无法自证）
     - 组织 → `友·宗门1` / `敌·宗门2` / `友·家族1` / `友·势力1` …
     - 境界 → `境界1~境界N`（**绝对阶梯**，按书中境界低→高排序）——
       不用"相对主角"的字母（C=当前会随主角升级漂移，同批概括语义全乱）
     每个代称带 `role_desc`（槽位功能说明）—— 计划生成时按说明**选角**，
     解决「模板 A 的男配10 与模板 B 的男配13 聚合时角色混乱」。
  ③ 正则替换：按原名长度降序（防子串截断），替换 summary / segment_summary / arc_summary。
  原文备份到 `*_raw` 列（可回滚）。

**book_aliases 是双向表**：正向匿名化；反向（代称 → 本书真实角色）供写正文时还原 ——
模板因此可跨书复用。
"""
import json
import logging
import re
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.orm import BookAliasORM, ChapterSummaryORM
from app.services.plot_import import RateLimiter, _ds_post, ds_key, parse_json_loose

logger = logging.getLogger(__name__)

_KIND_CN = {"role": "配角", "sect": "宗门", "family": "家族",
            "force": "势力", "place": "地点", "item": "物品"}
_BATCH_CHAPTERS = 30          # cast 抽取每次送多少章的概括
_ALLY = "ally"


# ---------------------------------------------------------------------------
# ① cast 抽取（LLM）
# ---------------------------------------------------------------------------
def _extract_prompt(summaries: list[str]) -> str:
    return (
        "下面是一部小说连续若干章的逐章概括。请抽取：\n"
        "1. `protagonist`：主角姓名（全篇同一个）\n"
        "2. `entities`：其他角色与组织/地点/物品 —— name（名称）、kind（role=角色/sect=宗门/"
        "family=家族/force=势力/place=地点/item=物品）、relation（与主角关系：ally=非敌/"
        "enemy=敌对/neutral=未明确）、desc（一句话功能说明，如「主角的师长，亦师亦友」）\n"
        "3. `realms`：修炼境界阶梯，**从低到高**列出名称\n"
        "概括里没提到的不要编造；relation 不明确就填 neutral。\n\n"
        "只输出 JSON（不要 markdown 代码块）：\n"
        '{"protagonist":"...","entities":[{"name":"...","kind":"role",'
        '"relation":"ally","desc":"..."}],"realms":["境界名从低到高"]}\n\n'
        + "\n".join(f"- {s}" for s in summaries)
    )


def extract_cast(db: Session, book_name: str, *, batch_chapters: int = _BATCH_CHAPTERS,
                 rate: RateLimiter | None = None) -> dict:
    """分批扫描全部章概括，抽取并合并 cast。"""
    key = ds_key(db)
    if not key:
        raise RuntimeError("未配置硅基流动 Key（app_configs.retrieval.siliconflow_key）")
    rate = rate or RateLimiter()
    rows = (db.query(ChapterSummaryORM)
            .filter_by(book_name=book_name)
            .order_by(ChapterSummaryORM.chapter_no).all())
    if not rows:
        raise RuntimeError(f"《{book_name}》没有概括数据")

    protagonist: str | None = None
    entities: dict[str, dict] = {}
    realm_first: dict[str, int] = {}   # 境界名 → 首现章号（比 LLM 自报排序更可靠）

    for i in range(0, len(rows), batch_chapters):
        chunk = rows[i:i + batch_chapters]
        # ⚠️ 读 raw（匿名化前的原文）：对已替换文本再抽取会产生「一星境界2」这类链条污染
        texts = [(r.summary_raw or r.summary or "") for r in chunk]
        raw = _ds_post(key, _extract_prompt(texts),
                       max_tokens=4000, temperature=0.1, rate=rate)
        data = parse_json_loose(raw) or {}
        if not protagonist and data.get("protagonist"):
            protagonist = str(data["protagonist"]).strip()
        for ent in data.get("entities") or []:
            name = str(ent.get("name") or "").strip()
            if not name or name == protagonist:
                continue
            kind = ent.get("kind") if ent.get("kind") in _KIND_CN else "role"
            prev = entities.get(name)
            if prev is None:
                entities[name] = {"name": name, "kind": kind,
                                  "relation": ent.get("relation") or "neutral",
                                  "desc": str(ent.get("desc") or "").strip(),
                                  "first_chapter": chunk[0].chapter_no}
            else:                       # 合并：desc 取更长，relation 敌对优先（保守）
                if len(str(ent.get("desc") or "")) > len(prev["desc"] or ""):
                    prev["desc"] = str(ent.get("desc") or "")
                if ent.get("relation") == "enemy":
                    prev["relation"] = "enemy"
        for r_name in data.get("realms") or []:
            r_name = str(r_name).strip()
            if not r_name or r_name in realm_first:
                continue
            # 丢弃子级条目（斗之气三段/一星斗者 —— 主境界已覆盖）与替换残留（境界2）
            if re.search(r"\d|[一二三四五六七八九十]+[星段阶]", r_name):
                continue
            realm_first[r_name] = chunk[0].chapter_no
        logger.info(f"[alias] cast 抽取进度 {min(i + batch_chapters, len(rows))}/{len(rows)} 章")

    # 阶梯按「首现章号」排序：主角前期境界低、后期境界高，首现顺序天然近似阶梯顺序
    # （LLM 自报的顺序不可靠，实测把「大斗师」排在了「斗师」前面）
    realms = sorted(realm_first, key=lambda n: realm_first[n])
    return {"protagonist": protagonist or "", "entities": list(entities.values()),
            "realms": realms, "chapters": len(rows)}


# ---------------------------------------------------------------------------
# ② 代称分配（纯代码）
# ---------------------------------------------------------------------------
def assign_aliases(cast: dict) -> list[dict]:
    """纯代码分配代称，返回 book_aliases 行（不含 id/时间）。"""
    out: list[dict] = []
    if cast.get("protagonist"):
        out.append({"original": cast["protagonist"], "alias": "主角",
                    "kind": "protagonist", "relation": _ALLY,
                    "role_desc": "主角", "first_chapter": None})
    counters: dict[tuple[str, str], int] = {}
    for ent in cast.get("entities") or []:
        kind = ent.get("kind") if ent.get("kind") in _KIND_CN else "role"
        prefix = "敌" if ent.get("relation") == "enemy" else "友"
        key = (kind, prefix)
        counters[key] = counters.get(key, 0) + 1
        out.append({
            "original": ent["name"],
            "alias": f"{prefix}·{_KIND_CN[kind]}{counters[key]}",
            "kind": kind,
            "relation": ent.get("relation") or "neutral",
            "role_desc": ent.get("desc") or "",
            "first_chapter": ent.get("first_chapter"),
        })
    for idx, r_name in enumerate(cast.get("realms") or [], start=1):
        out.append({"original": r_name, "alias": f"境界{idx}",
                    "kind": "realm", "relation": "neutral",
                    "role_desc": "本书境界阶梯（绝对序，低→高）", "first_chapter": None})
    return out


# ---------------------------------------------------------------------------
# ③ 正则替换（长名优先，防子串截断）
# ---------------------------------------------------------------------------
def _replace_all(text: str, pairs: list[tuple[str, str]]) -> str:
    if not text:
        return text
    for original, alias in pairs:
        if original and original in text:
            text = text.replace(original, alias)
    return text


def apply_replacement(db: Session, book_name: str, mapping: list[dict]) -> dict:
    """把全书概括文本里的原名替换为代称（原文备份到 *_raw，幂等：raw 已存在则不覆盖）。"""
    pairs = sorted(((m["original"], m["alias"]) for m in mapping),
                   key=lambda p: -len(p[0]))
    rows = db.query(ChapterSummaryORM).filter_by(book_name=book_name).all()
    touched = 0
    for r in rows:
        if r.summary_raw is None:
            r.summary_raw = r.summary
        if r.segment_summary_raw is None and r.segment_summary:
            r.segment_summary_raw = r.segment_summary
        if r.arc_summary_raw is None and r.arc_summary:
            r.arc_summary_raw = r.arc_summary
        new_summary = _replace_all(r.summary_raw or r.summary, pairs)
        new_seg = _replace_all(r.segment_summary_raw or r.segment_summary or "", pairs)
        new_arc = _replace_all(r.arc_summary_raw or r.arc_summary or "", pairs)
        if new_summary != r.summary or new_seg != r.segment_summary or new_arc != r.arc_summary:
            touched += 1
        r.summary, r.segment_summary, r.arc_summary = new_summary, new_seg, new_arc
    db.commit()
    return {"chapters": len(rows), "touched": touched}


# ---------------------------------------------------------------------------
# 全流程
# ---------------------------------------------------------------------------
def anonymize_book(db: Session, book_name: str, *, batch_chapters: int = _BATCH_CHAPTERS) -> dict:
    """抽取 → 分配 → 写 book_aliases → 替换概括文本。幂等：重复跑会重建映射并再次替换
    （已匿名文本中的原名已消失，替换为 no-op；新增的原名会被补上）。"""
    cast = extract_cast(db, book_name, batch_chapters=batch_chapters)
    if not cast.get("chapters"):
        raise RuntimeError(f"《{book_name}》没有概括数据（先跑 --stage summarize）")
    mapping = assign_aliases(cast)

    # 写映射表（同 (book, original) 覆盖更新）
    db.query(BookAliasORM).filter_by(book_name=book_name).delete()
    for m in mapping:
        db.add(BookAliasORM(id=uuid.uuid4().hex, book_name=book_name,
                            original=m["original"], alias=m["alias"], kind=m["kind"],
                            relation=m["relation"], role_desc=m["role_desc"],
                            first_chapter=m.get("first_chapter"),
                            created_at=datetime.utcnow()))
    db.commit()

    rep = apply_replacement(db, book_name, mapping)
    logger.info(f"[alias] 《{book_name}》匿名化完成：{len(mapping)} 条映射，"
                f"触及 {rep['touched']}/{rep['chapters']} 章")
    return {"aliases": len(mapping), **rep,
            "protagonist": cast.get("protagonist"),
            "realms": cast.get("realms") or []}


def get_aliases(db: Session, book_name: str) -> list[dict]:
    """读映射表（供审核界面 / 计划生成的槽位说明）。"""
    rows = (db.query(BookAliasORM)
            .filter_by(book_name=book_name)
            .order_by(BookAliasORM.kind, BookAliasORM.alias).all())
    return [{"original": r.original, "alias": r.alias, "kind": r.kind,
             "relation": r.relation, "role_desc": r.role_desc} for r in rows]
