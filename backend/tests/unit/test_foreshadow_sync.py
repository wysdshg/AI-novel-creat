"""Phase 2.1 伏笔回注单测。

覆盖三件事：
1. **回注语义**：bury → 新建待回收；hint → 关联场景；resolve → 标记已回收；
2. **去重与幂等**（这块最关键）：同一伏笔换个说法要能匹配上、同一章重跑不能翻倍；
3. 基础 CRUD 与「可触发伏笔」筛选。

不触网、不依赖模型：纯表驱动。
"""
import uuid

import pytest

from app.models.orm import ForeshadowORM
from app.services import foreshadow_crud as svc


def _actions(*pairs):
    """pairs: (action, desc)"""
    return [{"action": a, "desc": d} for a, d in pairs]


def _all(db, pid="p1"):
    return db.query(ForeshadowORM).filter_by(project_id=pid).all()


# ---------------- 回注语义 ----------------

def test_bury_creates_pending(test_db):
    stats = svc.sync_from_actions(test_db, "p1", 3,
                                  _actions(("bury", "陆离腰间那枚残缺玉佩的来历")))
    test_db.commit()
    assert stats["created"] == 1
    rows = _all(test_db)
    assert len(rows) == 1
    f = rows[0]
    assert f.status == "pending"
    assert f.buried_chapter == 3
    assert "玉佩" in f.description
    assert f.enabled is True


def test_hint_attaches_scene_to_existing(test_db):
    svc.sync_from_actions(test_db, "p1", 1, _actions(("bury", "城隍庙铜牌上的古怪符号")))
    stats = svc.sync_from_actions(test_db, "p1", 4, _actions(("hint", "城隍庙铜牌上的古怪符号")))
    test_db.commit()
    rows = _all(test_db)
    assert len(rows) == 1, "hint 不应新建记录"
    assert stats["hinted"] == 1
    assert "第4章" in (rows[0].scene or "")


def test_resolve_marks_done(test_db):
    svc.sync_from_actions(test_db, "p1", 2, _actions(("bury", "沈砚袖中的半张残图")))
    stats = svc.sync_from_actions(test_db, "p1", 9, _actions(("resolve", "沈砚袖中的半张残图")))
    test_db.commit()
    rows = _all(test_db)
    assert len(rows) == 1
    assert stats["resolved"] == 1
    assert rows[0].status == "done"
    assert rows[0].activated_chapter == 9


def test_resolve_without_prior_bury_keeps_trace(test_db):
    """模型说"回收了"但我们没登记过 → 建一条 done 记录留痕，而不是丢弃。"""
    stats = svc.sync_from_actions(test_db, "p1", 7, _actions(("resolve", "某个从未登记过的旧怨")))
    test_db.commit()
    rows = _all(test_db)
    assert stats["orphan_resolve"] == 1
    assert len(rows) == 1
    assert rows[0].status == "done"
    assert rows[0].buried_chapter is None
    assert rows[0].activated_chapter == 7


# ---------------- 去重与幂等（核心） ----------------

def test_idempotent_on_reingest_same_chapter(test_db):
    """同一章重跑摄取（重生成/重跑 memory ingest）不得翻倍。"""
    acts = _actions(("bury", "铜牌上的符号与二十年前血案有关"),
                    ("hint", "玄真子的旧伤"))
    svc.sync_from_actions(test_db, "p1", 5, acts)
    test_db.commit()
    n1 = len(_all(test_db))

    svc.sync_from_actions(test_db, "p1", 5, acts)
    svc.sync_from_actions(test_db, "p1", 5, acts)
    test_db.commit()
    assert len(_all(test_db)) == n1 == 2, f"重跑导致翻倍：{len(_all(test_db))}"


def test_dedup_across_wording_variants(test_db):
    """同一伏笔换个说法（LLM 自由文本）应匹配到同一条。"""
    svc.sync_from_actions(test_db, "p1", 1,
                          _actions(("bury", "城隍庙雨夜拾得的铜牌上刻着古怪符号")))
    test_db.commit()
    # 第 6 章换个措辞再提到它
    stats = svc.sync_from_actions(test_db, "p1", 6,
                                  _actions(("hint", "城隍庙雨夜拾得的铜牌上刻着诡异符号")))
    test_db.commit()
    assert len(_all(test_db)) == 1, "措辞微调不应新建"
    assert stats["hinted"] == 1


def test_different_foreshadows_are_not_merged(test_db):
    """不相关的内容不能被误判成同一条。"""
    svc.sync_from_actions(test_db, "p1", 1, _actions(("bury", "铜牌上的古怪符号")))
    svc.sync_from_actions(test_db, "p1", 2, _actions(("bury", "药王谷禁地里的血色药炉")))
    test_db.commit()
    assert len(_all(test_db)) == 2


def test_short_similar_descriptions_not_merged(test_db):
    """⚠️回归：短描述只差一两个字时比率极高，不能被并成一条。

    「甲的伏笔线索」vs「乙的伏笔线索」（6 字差 1 字）difflib 比率 0.833，
    若不加长度门槛就会被误判成同一伏笔 → 两个独立伏笔丢失一个。
    """
    svc.sync_from_actions(test_db, "p1", 1, _actions(("bury", "甲的伏笔线索")))
    svc.sync_from_actions(test_db, "p1", 1, _actions(("bury", "乙的伏笔线索")))
    test_db.commit()
    assert len(_all(test_db)) == 2, "短且相似的两条伏笔不应被合并"


def test_bury_after_resolve_same_desc_no_duplicate(test_db):
    """已回收的伏笔又被抽出同一条（重跑/复述）→ 不重复建，保持 done。"""
    svc.sync_from_actions(test_db, "p1", 1, _actions(("bury", "沈砚怀中那枚青铜剑鞘的铭文")))
    svc.sync_from_actions(test_db, "p1", 3, _actions(("resolve", "沈砚怀中那枚青铜剑鞘的铭文")))
    test_db.commit()
    stats = svc.sync_from_actions(test_db, "p1", 8,
                                  _actions(("bury", "沈砚怀中那枚青铜剑鞘的铭文")))
    test_db.commit()
    rows = _all(test_db)
    assert len(rows) == 1, "同一条已回收伏笔不应重复登记"
    assert rows[0].status == "done"
    assert stats["skipped"] == 1


def test_new_thread_with_different_desc_creates_new(test_db):
    """回收后埋下**另一条**伏笔 → 正常新建（证明确实按内容区分）。"""
    svc.sync_from_actions(test_db, "p1", 1, _actions(("bury", "沈砚怀中那枚青铜剑鞘的铭文")))
    svc.sync_from_actions(test_db, "p1", 3, _actions(("resolve", "沈砚怀中那枚青铜剑鞘的铭文")))
    svc.sync_from_actions(test_db, "p1", 8, _actions(("bury", "幽冥殿深处那口锁着铁链的古井")))
    test_db.commit()
    rows = sorted(_all(test_db), key=lambda r: r.buried_chapter or 0)
    assert len(rows) == 2
    assert rows[0].status == "done"
    assert rows[1].status == "pending" and rows[1].buried_chapter == 8


def test_empty_and_malformed_actions_are_safe(test_db):
    assert svc.sync_from_actions(test_db, "p1", 1, [])["created"] == 0
    assert svc.sync_from_actions(test_db, "p1", 1, None)["created"] == 0
    # 缺 desc / 非 dict 项 → 跳过，不抛
    stats = svc.sync_from_actions(test_db, "p1", 1,
                                  [{"action": "bury"}, "纯字符串", {"desc": "有效伏笔"}])
    test_db.commit()
    assert stats["created"] == 1


# ---------------- 查询与 CRUD ----------------

def test_list_filter_and_active(test_db):
    svc.sync_from_actions(test_db, "p1", 1, _actions(("bury", "城隍庙铜牌上的古怪符号"),
                                                     ("bury", "药王谷禁地里的血色药炉")))
    svc.sync_from_actions(test_db, "p1", 2, _actions(("resolve", "城隍庙铜牌上的古怪符号")))
    test_db.commit()

    pend = svc.list_foreshadows(test_db, "p1", status="pending")
    done = svc.list_foreshadows(test_db, "p1", status="done")
    assert len(pend) == 1 and len(done) == 1
    assert len(svc.list_foreshadows(test_db, "p1")) == 2

    active = svc.get_active_foreshadows(test_db, "p1")
    assert len(active) == 1 and active[0]["description"].startswith("药王谷")


def test_disabled_foreshadow_excluded_from_active(test_db):
    svc.sync_from_actions(test_db, "p1", 1, _actions(("bury", "被停用的线索")))
    test_db.commit()
    fid = _all(test_db)[0].id
    svc.update_foreshadow(test_db, "p1", fid, _Dummy({"enabled": False}))
    assert svc.get_active_foreshadows(test_db, "p1") == []


def test_crud_create_update_delete(test_db):
    created = svc.create_foreshadow(test_db, "p1", _Dummy({
        "description": "手工登记的伏笔", "buried_chapter": 2,
        "trigger_condition": "主角踏进旧宅", "status": "pending"}))
    fid = created["id"]
    assert created["status"] == "pending"

    updated = svc.update_foreshadow(test_db, "p1", fid,
                                    _Dummy({"trigger_condition": "主角看见旧照片"}))
    assert updated["trigger_condition"] == "主角看见旧照片"

    act = svc.activate_foreshadow(test_db, "p1", fid, activated_chapter=12)
    assert act["status"] == "done" and act["activated_chapter"] == 12

    assert svc.delete_foreshadow(test_db, "p1", fid) is True
    assert svc.delete_foreshadow(test_db, "p1", fid) is False


def test_project_isolation(test_db):
    svc.sync_from_actions(test_db, "p1", 1, _actions(("bury", "p1 的伏笔")))
    svc.sync_from_actions(test_db, "p2", 1, _actions(("bury", "p2 的伏笔")))
    test_db.commit()
    assert len(svc.list_foreshadows(test_db, "p1")) == 1
    assert len(svc.list_foreshadows(test_db, "p2")) == 1


class _Dummy:
    """最小替身：让 crud 的 model_dump 分支可用（模拟 Pydantic 入参）。"""

    def __init__(self, data):
        self._d = data

    def model_dump(self, exclude_unset=False):
        return dict(self._d)
