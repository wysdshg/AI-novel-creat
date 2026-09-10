"""Phase 4.1 最小 eval：版本留档 / 打分 / 对比 / 级联。

覆盖重点（都是容易出错、且出了问题用户不一定看得见的地方）：
- **留档是旁路**：db 坏了也必须返回 None 而不是抛异常（不能影响生成主链路）
- **分数越界 / 版本不存在**：返回 None（不静默写脏数据）
- **重复打分**：历史保留、取最新（"最新"的判定依赖 created_at 排序）
- **级联**：删章要连带清版本与评分，且**不能误伤别的章**
"""
from app.schemas.chapter import ChapterCreate
from app.services import chapter_crud, eval_crud

PID = "p-eval-1"


def _mk(db, chapter_id="c1", content="正文" * 100, **kw):
    """留档一个版本（测试用默认值）。"""
    return eval_crud.record_variant(
        db, PID, chapter_id,
        article_id=kw.pop("article_id", "a1"),
        title=kw.pop("title", "第1章"),
        content=content,
        config_snapshot=kw.pop("config_snapshot", {"model_name": "m1", "temperature": 0.75}),
        metrics=kw.pop("metrics", {"duration_ms": 1234}),
    )


# ---------------------------------------------------------------------------
# 留档
# ---------------------------------------------------------------------------
class TestRecordVariant:
    def test_basic(self, test_db):
        v = _mk(test_db)
        assert v is not None
        assert v.chapter_id == "c1"
        assert v.article_id == "a1"
        assert v.word_count == len("正文" * 100)
        assert v.config_snapshot["model_name"] == "m1"
        assert v.metrics["duration_ms"] == 1234

    def test_empty_content_word_count_zero(self, test_db):
        assert _mk(test_db, content="").word_count == 0

    def test_body_snapshot_is_independent_of_chapter(self, test_db):
        """正文整存：改了原章也不影响已留档的版本（这正是评估能对比的前提）。"""
        v = _mk(test_db, content="原始版本正文")
        got = eval_crud.get_variant(test_db, v.id)
        assert got["content"] == "原始版本正文"

    def test_never_raises_when_db_broken(self, test_db):
        """留档是旁路：db 异常必须吞掉并返回 None，绝不上抛。"""

        class Boom:
            def add(self, *_):
                raise RuntimeError("db down")

            def commit(self):
                raise RuntimeError("db down")

            def rollback(self):
                raise RuntimeError("db down")

        assert eval_crud.record_variant(Boom(), PID, "c1", content="x") is None


# ---------------------------------------------------------------------------
# 打分
# ---------------------------------------------------------------------------
class TestScore:
    def test_score_ok(self, test_db):
        v = _mk(test_db)
        r = eval_crud.score_variant(test_db, v.id, 5, "很好")
        assert r["score"] == 5
        assert r["comment"] == "很好"

    def test_out_of_range_rejected(self, test_db):
        v = _mk(test_db)
        assert eval_crud.score_variant(test_db, v.id, 0) is None
        assert eval_crud.score_variant(test_db, v.id, 6) is None
        assert eval_crud.score_variant(test_db, v.id, -1) is None

    def test_bool_rejected(self, test_db):
        """True/False 是 int 的子类，必须显式挡掉（否则 True 会被当成分数 1）。"""
        v = _mk(test_db)
        assert eval_crud.score_variant(test_db, v.id, True) is None

    def test_missing_variant(self, test_db):
        assert eval_crud.score_variant(test_db, "no-such-variant", 3) is None

    def test_latest_score_wins(self, test_db):
        v = _mk(test_db)
        eval_crud.score_variant(test_db, v.id, 2)
        eval_crud.score_variant(test_db, v.id, 4)
        assert eval_crud.get_variant(test_db, v.id)["score"] == 4

    def test_history_kept(self, test_db):
        from app.models.orm import EvalRecordORM

        v = _mk(test_db)
        eval_crud.score_variant(test_db, v.id, 2)
        eval_crud.score_variant(test_db, v.id, 4)
        assert test_db.query(EvalRecordORM).filter_by(variant_id=v.id).count() == 2


# ---------------------------------------------------------------------------
# 列表 / 对比
# ---------------------------------------------------------------------------
class TestListAndSummary:
    def test_list_newest_first(self, test_db):
        _mk(test_db, content="A")
        v2 = _mk(test_db, content="B")
        items = eval_crud.list_variants(test_db, "c1")
        assert len(items) == 2
        assert items[0]["id"] == v2.id

    def test_list_with_content(self, test_db):
        _mk(test_db, content="ABC")
        assert eval_crud.list_variants(test_db, "c1", with_content=True)[0]["content"] == "ABC"

    def test_list_without_content_by_default(self, test_db):
        _mk(test_db, content="ABC")
        assert "content" not in eval_crud.list_variants(test_db, "c1")[0]

    def test_summary_picks_best(self, test_db):
        v1 = _mk(test_db, content="A")
        v2 = _mk(test_db, content="B")
        _mk(test_db, content="C")
        eval_crud.score_variant(test_db, v1.id, 3)
        eval_crud.score_variant(test_db, v2.id, 5)
        s = eval_crud.summarize(test_db, "c1")
        assert s["total"] == 3
        assert s["scored_count"] == 2
        assert s["avg_score"] == 4.0
        assert s["best"]["id"] == v2.id
        assert s["best"]["score"] == 5

    def test_summary_empty(self, test_db):
        s = eval_crud.summarize(test_db, "no-such-chapter")
        assert s == {"total": 0, "scored_count": 0, "avg_score": None, "best": None, "variants": []}


# ---------------------------------------------------------------------------
# 删除 / 级联
# ---------------------------------------------------------------------------
class TestDelete:
    def test_delete_variant_removes_scores(self, test_db):
        from app.models.orm import EvalRecordORM

        v = _mk(test_db)
        eval_crud.score_variant(test_db, v.id, 4)
        assert eval_crud.delete_variant(test_db, v.id) is True
        assert eval_crud.get_variant(test_db, v.id) is None
        assert test_db.query(EvalRecordORM).filter_by(variant_id=v.id).count() == 0

    def test_delete_missing_returns_false(self, test_db):
        assert eval_crud.delete_variant(test_db, "no-such-variant") is False

    def test_delete_by_chapter_scoped(self, test_db):
        """只删该章；别的章必须原样保留（作用域回归）。"""
        c1a = _mk(test_db, chapter_id="c1")
        _mk(test_db, chapter_id="c1")
        c1a_id = c1a.id  # 先取出：bulk delete 后对象不可再访问属性
        _mk(test_db, chapter_id="c2")
        eval_crud.score_variant(test_db, c1a_id, 3)
        assert eval_crud.delete_by_chapter(test_db, "c1") == 2
        assert eval_crud.list_variants(test_db, "c1") == []
        assert len(eval_crud.list_variants(test_db, "c2")) == 1

    def test_delete_chapter_cascades(self, test_db):
        """删章要连带清版本与评分 —— 否则留下带正文的孤儿版本，污染对比列表。"""
        from app.models.orm import EvalRecordORM

        ch = chapter_crud.create_chapter(
            test_db, PID,
            ChapterCreate(chapter_no=1, title="第1章", content="正文", word_count=2, article_id="a1"),
        )
        v = _mk(test_db, chapter_id=ch.id)
        vid = v.id  # 先取出（同上）
        eval_crud.score_variant(test_db, vid, 5)

        assert chapter_crud.delete_chapter(test_db, PID, ch.id) is True
        assert eval_crud.list_variants(test_db, ch.id) == []
        assert test_db.query(EvalRecordORM).filter_by(variant_id=vid).count() == 0
