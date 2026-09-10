"""伏笔 CRUD + 写后回注（Phase 2.1）。

背景（docs/02 §2 记录的断链）：`ingestion.py` 每章都在抽取 `foreshadow_actions`
并塞进 `ChapterMemoryORM`，但**全项目没有任何代码写 `ForeshadowORM`** —— AI 白干，
数据断在最后一米。同时 `context/layers.py:layer_foreshadows` 的**读路径早就写好了**
（读 enabled 的 pending 伏笔注入生成上下文），只是表里永远没数据。

本模块补齐写入侧：
- `sync_from_actions()`：把一章的 `foreshadow_actions` 回注进 `foreshadows` 表
  （bury → 新建待回收；hint → 关联触发场景；resolve → 标记已回收）；
- 基础 CRUD，供路由层使用。

**去重是核心难点**：描述来自 LLM 自由文本，同一伏笔在不同章可能被写成不同措辞，
而 ingestion 可能对同一章重跑。故匹配用三级策略（归一化相等 → 互相包含 → difflib 相似），
保证「同一伏笔不重复建、重跑不翻倍」。
"""
import difflib
import re
import uuid

from sqlalchemy.orm import Session

from app.models.orm import ForeshadowORM

# 相似判定阈值：difflib 比率 ≥ 此值视为同一伏笔
_SIM_THRESHOLD = 0.85
# 模糊匹配的最小长度门槛（**关键**）：短描述只差一两个字，比率就会很高——
# 实测「甲的伏笔线索」vs「乙的伏笔线索」（6 字，差 1 字）比率 0.833，会被误判成同一条。
# 故只有双方都够长（≥12 字）时才启用模糊匹配；短描述只认「归一化完全相等」。
_SIM_MIN_LEN = 12
# 互相包含判定的最小长度（太短（如"铜牌"）包含关系容易误判）
_MIN_CONTAIN_LEN = 6

_PUNCT = re.compile(r"[\s，。、；：！？·—…“”‘’（）()\[\]【】《》\"'’]+")


def _norm(text: str) -> str:
    """归一化：去标点空白，便于同义描述对齐。"""
    return _PUNCT.sub("", (text or "").strip()).lower()


def _is_same(desc_a: str, desc_b: str) -> bool:
    """判断两条伏笔描述是否指同一件事。

    三级策略（从严到松，逐级放宽但都有门槛）：
      1. 归一化后完全相等；
      2. 互相包含（双方都 ≥6 字，避免"铜牌"/"铜牌上的符号"这类误判）；
      3. difflib 相似度 ≥0.85 且**双方都 ≥12 字**——短描述差一两字比率就很高，
         不设长度门槛会把「甲的伏笔线索」和「乙的伏笔线索」并成一条。
    """
    a, b = _norm(desc_a), _norm(desc_b)
    if not a or not b:
        return False
    if a == b:
        return True
    if min(len(a), len(b)) >= _MIN_CONTAIN_LEN and (a in b or b in a):
        return True
    if min(len(a), len(b)) < _SIM_MIN_LEN:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= _SIM_THRESHOLD


def _find_match(db: Session, project_id: str, desc: str,
                statuses: tuple[str, ...] = ("pending", "active")) -> ForeshadowORM | None:
    """在已登记的伏笔里找与 desc 指同一件事的那条（优先最近埋下的）。"""
    rows = (
        db.query(ForeshadowORM)
        .filter_by(project_id=project_id)
        .filter(ForeshadowORM.status.in_(statuses))
        .order_by(ForeshadowORM.buried_chapter.desc().nullslast())
        .all()
    )
    for r in rows:
        if _is_same(r.description or "", desc):
            return r
    return None


def sync_from_actions(db: Session, project_id: str, chapter_no: int,
                      actions: list[dict] | None) -> dict:
    """把一章的伏笔动作回注到 `foreshadows` 表（幂等）。

    action 语义（来自 ingestion 的抽取提示词）：
      bury    埋下新伏笔 → 建 pending 记录
      hint    提及/暗示已有伏笔 → 关联触发场景（不算回收）
      resolve 回收/兑现伏笔 → 标记 done + activated_chapter

    幂等保证：同一章重跑不会重复建；`resolve` 只对匹配到的记录生效。
    返回统计 {created, hinted, resolved, skipped}。
    """
    stats = {"created": 0, "hinted": 0, "resolved": 0, "skipped": 0, "orphan_resolve": 0}
    actions = actions or []

    for item in actions:
        if not isinstance(item, dict):
            continue
        desc = str(item.get("desc") or item.get("description") or "").strip()
        if not desc:
            continue
        act = str(item.get("action") or "hint").strip().lower()
        scene_hint = f"第{chapter_no}章"

        if act == "resolve":
            hit = _find_match(db, project_id, desc, statuses=("pending", "active"))
            if hit is not None:
                if (hit.status or "pending") != "done":
                    hit.status = "done"
                    hit.activated_chapter = chapter_no
                    stats["resolved"] += 1
                else:
                    stats["skipped"] += 1
            else:
                # 模型说"回收了"但我们从没登记过它（漏抽/中途换模型）：
                # 建一条 done 记录留痕，而不是丢弃——至少作者能在列表里看到这条线已收。
                db.add(ForeshadowORM(
                    id=uuid.uuid4().hex, project_id=project_id,
                    description=desc, buried_chapter=None,
                    scene=scene_hint, enabled=True,
                    activated_chapter=chapter_no, status="done",
                ))
                db.flush()  # session autoflush=False：不 flush 则后续 _find_match 查不到刚加的记录
                stats["orphan_resolve"] += 1
            continue

        if act == "bury":
            hit = _find_match(db, project_id, desc, statuses=("pending", "active", "done"))
            if hit is not None:
                # 已登记过（重跑 / 换个说法）：补全埋设章号即可，不重复建
                if hit.buried_chapter is None:
                    hit.buried_chapter = chapter_no
                stats["skipped"] += 1
            else:
                db.add(ForeshadowORM(
                    id=uuid.uuid4().hex, project_id=project_id,
                    description=desc, buried_chapter=chapter_no,
                    scene=scene_hint, enabled=True, status="pending",
                ))
                db.flush()
                stats["created"] += 1
            continue

        # 其余（hint / 未知动作）→ 关联到已有伏笔，找不到就补建
        hit = _find_match(db, project_id, desc, statuses=("pending", "active"))
        if hit is not None:
            if not (hit.scene or "").strip():
                hit.scene = scene_hint
            elif scene_hint not in (hit.scene or ""):
                hit.scene = f"{hit.scene}、{scene_hint}"
            stats["hinted"] += 1
        else:
            db.add(ForeshadowORM(
                id=uuid.uuid4().hex, project_id=project_id,
                description=desc, buried_chapter=chapter_no,
                scene=scene_hint, enabled=True, status="pending",
            ))
            db.flush()
            stats["created"] += 1

    return stats


# ---------------------------------------------------------------------------
# 基础 CRUD（路由层使用）
# ---------------------------------------------------------------------------

def _to_dict(o: ForeshadowORM) -> dict:
    return {
        "id": o.id,
        "project_id": o.project_id,
        "description": o.description,
        "buried_chapter": o.buried_chapter,
        "scene": o.scene,
        "trigger_condition": o.trigger_condition,
        "enabled": bool(o.enabled),
        "activated_chapter": o.activated_chapter,
        "related_ids": list(o.related_ids or []),
        "status": o.status or "pending",
    }


def list_foreshadows(db: Session, project_id: str, status: str | None = None) -> list[dict]:
    q = db.query(ForeshadowORM).filter_by(project_id=project_id)
    if status:
        q = q.filter(ForeshadowORM.status == status)
    rows = q.order_by(ForeshadowORM.buried_chapter.desc().nullslast()).all()
    return [_to_dict(r) for r in rows]


def get_active_foreshadows(db: Session, project_id: str, limit: int = 20) -> list[dict]:
    """可触发伏笔 = 未回收（pending）且 enabled。生成前置检索用。"""
    rows = (
        db.query(ForeshadowORM)
        .filter_by(project_id=project_id, status="pending")
        .filter(ForeshadowORM.enabled.is_(True))
        .order_by(ForeshadowORM.buried_chapter.desc().nullslast())
        .limit(max(1, limit))
        .all()
    )
    return [_to_dict(r) for r in rows]


def create_foreshadow(db: Session, project_id: str, data) -> dict:
    payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)
    o = ForeshadowORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        description=payload.get("description") or "",
        buried_chapter=payload.get("buried_chapter"),
        scene=payload.get("scene"),
        trigger_condition=payload.get("trigger_condition"),
        enabled=bool(payload.get("enabled", True)),
        activated_chapter=payload.get("activated_chapter"),
        related_ids=list(payload.get("related_ids") or []),
        status=payload.get("status") or "pending",
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_dict(o)


def update_foreshadow(db: Session, project_id: str, foreshadow_id: str, data) -> dict | None:
    o = db.query(ForeshadowORM).filter_by(project_id=project_id, id=foreshadow_id).first()
    if o is None:
        return None
    payload = data.model_dump(exclude_unset=True) if hasattr(data, "model_dump") else dict(data)
    for k, v in payload.items():
        if v is not None and hasattr(o, k):
            setattr(o, k, v)
    db.commit()
    db.refresh(o)
    return _to_dict(o)


def delete_foreshadow(db: Session, project_id: str, foreshadow_id: str) -> bool:
    o = db.query(ForeshadowORM).filter_by(project_id=project_id, id=foreshadow_id).first()
    if o is None:
        return False
    db.delete(o)
    db.commit()
    return True


def activate_foreshadow(db: Session, project_id: str, foreshadow_id: str,
                        activated_chapter: int | None = None) -> dict | None:
    """标记伏笔已回收（status → done）。"""
    o = db.query(ForeshadowORM).filter_by(project_id=project_id, id=foreshadow_id).first()
    if o is None:
        return None
    o.status = "done"
    if activated_chapter is not None:
        o.activated_chapter = activated_chapter
    db.commit()
    db.refresh(o)
    return _to_dict(o)
