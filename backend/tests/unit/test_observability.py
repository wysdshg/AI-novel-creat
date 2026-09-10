"""Phase 4.2 / 4.3 观测消费端：用量计量 + 反馈回流。

覆盖重点：
- **usage 归一化**：三家厂商字段名不同（OpenAI / Claude / Ollama），必须都归一正确；
  两边都取不到时要返回 None，**不能硬造 0**（否则"没数据"会被记成"零消耗"）
- **估算标记**：厂商没回流 usage 时按字符估算，必须标 `estimated=True`
- **失败静默**：计量/记录都是旁路，db 坏了也不能抛（不能影响模型调用与正文保存）
- **改动判定**：只是保存一下（相似度≈1）不该记反馈，否则噪音淹没信号
- **改动统计**：similarity / change_ratio 计算方向正确（改动越大 → similarity 越小）
"""
import difflib

from app.core.gateway.base import BaseModelAdapter
from app.models.orm import ChapterVariantORM, FeedbackRecordORM, LlmUsageLogORM
from app.services import feedback_crud, usage_crud

PID = "p-obs-1"


class Boom:
    """模拟坏掉的 session：所有方法都抛。"""

    def add(self, *_):
        raise RuntimeError("db down")

    def commit(self):
        raise RuntimeError("db down")

    def rollback(self):
        raise RuntimeError("db down")


# ---------------------------------------------------------------------------
# usage：归一化
# ---------------------------------------------------------------------------
class TestNormalizeUsage:
    def test_openai_fields(self):
        u = BaseModelAdapter.normalize_usage({"prompt_tokens": 10, "completion_tokens": 20})
        assert u == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30,
                     "estimated": False}

    def test_claude_fields(self):
        u = BaseModelAdapter.normalize_usage(
            {"input_tokens": 5, "output_tokens": 7},
            prompt_key="input_tokens", completion_key="output_tokens")
        assert u["prompt_tokens"] == 5 and u["completion_tokens"] == 7

    def test_ollama_fields(self):
        u = BaseModelAdapter.normalize_usage(
            {"prompt_eval_count": 3, "eval_count": 4},
            prompt_key="prompt_eval_count", completion_key="eval_count")
        assert u["total_tokens"] == 7

    def test_missing_returns_none_not_zero(self):
        """取不到必须 None —— 硬造 0 会让"没数据"伪装成"零消耗"。"""
        assert BaseModelAdapter.normalize_usage({}) is None
        assert BaseModelAdapter.normalize_usage(None) is None
        assert BaseModelAdapter.normalize_usage({"other": 1}) is None

    def test_partial_field(self):
        """只有一半也算有数据（Ollama 的 done 帧有时只带其一）。"""
        u = BaseModelAdapter.normalize_usage({"eval_count": 9},
                                             prompt_key="prompt_eval_count", completion_key="eval_count")
        assert u["prompt_tokens"] == 0 and u["completion_tokens"] == 9


# ---------------------------------------------------------------------------
# usage：记录与统计
# ---------------------------------------------------------------------------
class TestRecordUsage:
    def test_estimate_tokens(self):
        assert usage_crud.estimate_tokens("") == 0
        assert usage_crud.estimate_tokens("a" * 15) == 10   # 15 / 1.5

    def test_record_real_usage(self, test_db):
        usage_crud.record_usage(test_db, scene="chapter", vendor="custom", model_name="m1",
                                usage={"prompt_tokens": 100, "completion_tokens": 200,
                                       "total_tokens": 300, "estimated": False},
                                project_id=PID)
        row = test_db.query(LlmUsageLogORM).one()
        assert row.total_tokens == 300
        assert row.estimated is False
        assert row.scene == "chapter"

    def test_record_estimated_when_no_usage(self, test_db):
        """厂商没回流 usage → 按字符估算并标 estimated=True。"""
        usage_crud.record_usage(test_db, scene="chapter", prompt_text="a" * 150,
                                completion_text="b" * 300, project_id=PID)
        row = test_db.query(LlmUsageLogORM).one()
        assert row.estimated is True
        assert row.prompt_tokens == 100 and row.completion_tokens == 200

    def test_nothing_to_record(self, test_db):
        """既没 usage 也没文本 → 不记空行（否则污染统计）。"""
        usage_crud.record_usage(test_db, scene="chapter", project_id=PID)
        assert test_db.query(LlmUsageLogORM).count() == 0

    def test_failed_call_still_recorded(self, test_db):
        """失败调用同样烧 token，必须记（ok=False）。"""
        usage_crud.record_usage(test_db, scene="chapter", ok=False,
                                usage={"prompt_tokens": 50, "completion_tokens": 0}, project_id=PID)
        row = test_db.query(LlmUsageLogORM).one()
        assert row.ok is False and row.total_tokens == 50

    def test_never_raises_when_db_broken(self):
        usage_crud.record_usage(Boom(), scene="chapter", usage={"prompt_tokens": 1},
                                completion_text="x")  # 不应抛异常


class TestUsageSummary:
    def _seed(self, db):
        usage_crud.record_usage(db, scene="chapter", model_name="m1", vendor="custom",
                                usage={"prompt_tokens": 100, "completion_tokens": 100}, project_id=PID)
        usage_crud.record_usage(db, scene="chapter", model_name="m2", vendor="custom",
                                usage={"prompt_tokens": 300, "completion_tokens": 300}, project_id=PID)
        usage_crud.record_usage(db, scene="discussion", model_name="m1", vendor="custom",
                                usage={"prompt_tokens": 50, "completion_tokens": 50}, project_id=PID)

    def test_overall(self, test_db):
        self._seed(test_db)
        s = usage_crud.summary(test_db, project_id=PID)
        assert s["overall"]["calls"] == 3
        assert s["overall"]["total_tokens"] == 900

    def test_by_model_sorted_desc(self, test_db):
        self._seed(test_db)
        s = usage_crud.summary(test_db, project_id=PID)
        assert s["by_model"][0]["model_name"] == "m2"      # 600 token 最多
        assert len(s["by_scene"]) == 2

    def test_trend_has_today(self, test_db):
        self._seed(test_db)
        s = usage_crud.summary(test_db, project_id=PID)
        assert len(s["trend"]) == 1

    def test_recent_list(self, test_db):
        self._seed(test_db)
        s = usage_crud.summary(test_db, project_id=PID)
        assert len(s["recent"]) == 3

    def test_empty(self, test_db):
        s = usage_crud.summary(test_db, project_id="nobody")
        assert s["overall"]["calls"] == 0 and s["by_model"] == []

    def test_project_filter(self, test_db):
        """项目隔离：别的项目的用量不能串进来。"""
        self._seed(test_db)
        usage_crud.record_usage(test_db, scene="chapter", model_name="other",
                                usage={"prompt_tokens": 9999}, project_id="other-p")
        s = usage_crud.summary(test_db, project_id=PID)
        assert s["overall"]["total_tokens"] == 900

    def test_clear(self, test_db):
        self._seed(test_db)
        assert usage_crud.clear(test_db, project_id=PID) == 3
        assert test_db.query(LlmUsageLogORM).count() == 0


# ---------------------------------------------------------------------------
# feedback：改动捕获
# ---------------------------------------------------------------------------
class TestRecordChapterEdit:
    def test_no_change_not_recorded(self, test_db):
        assert feedback_crud.record_chapter_edit(test_db, PID, "c1", "同样的文本", "同样的文本") is None
        assert test_db.query(FeedbackRecordORM).count() == 0

    def test_trivial_change_not_recorded(self, test_db):
        """只是重存一下（相似度≈1）不该记 —— 否则噪音淹没真实信号。"""
        base = "这是一段很长的正文。" * 50
        assert feedback_crud.record_chapter_edit(test_db, PID, "c1", base, base + " ") is None

    def test_real_edit_recorded(self, test_db):
        before = "第一段内容。第二段内容。第三段内容。"
        after = "第一段内容。第三段内容。"          # 删掉一段
        d = feedback_crud.record_chapter_edit(test_db, PID, "c1", before, after)
        assert d is not None
        assert d["before_len"] == len(before)
        assert d["after_len"] == len(after)
        assert d["delta_len"] < 0
        row = test_db.query(FeedbackRecordORM).one()
        assert row.kind == "chapter_edit" and row.target_id == "c1"

    def test_change_ratio_direction(self, test_db):
        """改动越大 → similarity 越小、change_ratio 越大。"""
        base = "甲乙丙丁戊己庚辛壬癸" * 20
        small = feedback_crud.record_chapter_edit(test_db, PID, "c1", base, base[:-5] + "XXXXX")
        big = feedback_crud.record_chapter_edit(test_db, PID, "c1", base, "完全换了一段全新的文字" * 5)
        assert big["change_ratio"] > small["change_ratio"]

    def test_links_latest_variant(self, test_db):
        """有留档版本时应关联上（便于回溯"作者改的是哪一版 AI 产出"）。"""
        v = ChapterVariantORM(id="v1", project_id=PID, chapter_id="c1",
                              content="原始", word_count=2, config_snapshot={}, metrics={})
        test_db.add(v)
        test_db.commit()
        d = feedback_crud.record_chapter_edit(test_db, PID, "c1", "原始正文内容", "改过的正文")
        assert d is not None
        assert test_db.query(FeedbackRecordORM).one().variant_id == "v1"

    def test_no_variant_ok(self, test_db):
        """没有留档版本时也要能记（variant_id 为空）。"""
        d = feedback_crud.record_chapter_edit(test_db, PID, "c1", "AAAAAAAAAA", "BBBBBBBBBB")
        assert d is not None
        assert test_db.query(FeedbackRecordORM).one().variant_id is None

    def test_never_raises_when_db_broken(self):
        assert feedback_crud.record_chapter_edit(Boom(), PID, "c1", "AAAA", "BBBB") is None


class TestFeedbackStats:
    def test_empty(self, test_db):
        s = feedback_crud.stats(test_db, project_id=PID)
        assert s["total"] == 0 and s["avg_change_ratio"] is None

    def test_stats_and_list(self, test_db):
        base = "一二三四五六七八九十" * 10
        feedback_crud.record_chapter_edit(test_db, PID, "c1", base, base[:-20])
        feedback_crud.record_chapter_edit(test_db, PID, "c2", base, "全新内容" * 10)
        s = feedback_crud.stats(test_db, project_id=PID)
        assert s["total"] == 2
        assert s["by_kind"]["chapter_edit"] == 2
        assert 0 < s["avg_similarity"] < 1
        assert feedback_crud.list_feedback(test_db, project_id=PID)[0]["kind"] == "chapter_edit"

    def test_project_filter(self, test_db):
        base = "一二三四五六七八九十" * 10
        feedback_crud.record_chapter_edit(test_db, PID, "c1", base, base[:-20])
        feedback_crud.record_chapter_edit(test_db, "other-p", "c9", base, "完全不同" * 10)
        assert feedback_crud.stats(test_db, project_id=PID)["total"] == 1
        assert feedback_crud.stats(test_db, project_id="other-p")["total"] == 1

    def test_clear(self, test_db):
        base = "一二三四五六七八九十" * 10
        feedback_crud.record_chapter_edit(test_db, PID, "c1", base, base[:-20])
        assert feedback_crud.clear(test_db, project_id=PID) == 1
        assert test_db.query(FeedbackRecordORM).count() == 0
