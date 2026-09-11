"""Phase 7.1 情节段切分：写入正确性 / 兜底 / **断点续跑** / 并发顺序。

背景（2026-09-11）：段切分是**全书序列**操作，长任务会被外部超时中断
（实测 OpenCode 的 shell 有 25 分钟超时）。若每次重跑都从零重算，存在
「反复超时、永远跑不完」的风险 → 改为**前缀式断点续跑**（已完成批次跳过、段号续接）。
"""
import json
import re as _re

from app.services import plot_import as pi


def _seed(test_db, nos):
    for no in nos:
        test_db.add(pi.ChapterSummaryORM(
            id=f"s{no}", book_name="书", chapter_no=no, summary=f"第{no}章概括"))
    test_db.commit()


def _mock_seg(monkeypatch, payload):
    """段切分走 `_sf_post`（无 db 依赖），需同时给 `sf_key` 打桩。"""
    monkeypatch.setattr(pi, "sf_key", lambda db: "k")
    if callable(payload):
        monkeypatch.setattr(pi, "_sf_post", payload)
    else:
        monkeypatch.setattr(pi, "_sf_post", lambda k, c, **kw: payload)


def _rows(test_db):
    return test_db.query(pi.ChapterSummaryORM).order_by(
        pi.ChapterSummaryORM.chapter_no).all()


class TestSegmentBasics:
    def test_writeback(self, test_db, monkeypatch):
        _seed(test_db, [1, 2, 3, 4])
        raw = json.dumps({"segments": [
            {"chapters": [1, 2], "summary": "段一概括"},
            {"chapters": [3, 4], "summary": "段二概括"},
        ]}, ensure_ascii=False)
        _mock_seg(monkeypatch, raw)
        r = pi.segment_chapters(test_db, "书", batch=10)
        assert r["segments"] == 2 and r["batches_run"] == 1
        rows = _rows(test_db)
        assert [x.segment_no for x in rows] == [1, 1, 2, 2]
        assert rows[0].segment_summary == "段一概括"

    def test_uncovered_chapter_falls_back(self, test_db, monkeypatch):
        """LLM 漏标第 3 章 → 兜底归入最后一段（保证全覆盖）。"""
        _seed(test_db, [1, 2, 3])
        _mock_seg(monkeypatch, json.dumps(
            {"segments": [{"chapters": [1, 2], "summary": "段一"}]}, ensure_ascii=False))
        r = pi.segment_chapters(test_db, "书", batch=10)
        rows = _rows(test_db)
        assert rows[2].segment_no == 1
        assert r["segments"] == 1

    def test_bad_json_falls_back_single_segment(self, test_db, monkeypatch):
        _seed(test_db, [1, 2])
        _mock_seg(monkeypatch, "这不是JSON")
        r = pi.segment_chapters(test_db, "书", batch=10)
        assert r["segments"] == 1
        assert all(x.segment_no == 1 for x in _rows(test_db))

    def test_force_clears_old(self, test_db, monkeypatch):
        """force=True → 清旧标记整体重算（默认不 force 时是续跑，见下个类）。"""
        _seed(test_db, [1, 2])
        test_db.query(pi.ChapterSummaryORM).update({"segment_no": 9})
        test_db.commit()
        _mock_seg(monkeypatch, json.dumps(
            {"segments": [{"chapters": [1, 2], "summary": "新段"}]}))
        pi.segment_chapters(test_db, "书", batch=10, force=True)
        assert all(x.segment_no == 1 for x in _rows(test_db))


class TestSegmentResume:
    """断点续跑：已完成批次跳过、段号续接、只跑未完成部分。"""

    def test_skips_completed_batches_and_continues_seg_no(self, test_db, monkeypatch):
        _seed(test_db, [1, 2, 3, 4])
        # 第 1 批（章 1、2）已完成，占用段号 1
        test_db.query(pi.ChapterSummaryORM).filter(
            pi.ChapterSummaryORM.chapter_no.in_([1, 2])
        ).update({"segment_no": 1, "segment_summary": "旧段"}, synchronize_session=False)
        test_db.commit()

        called: list[str] = []

        def fake_post(k, c, **kw):
            called.append(c)
            return json.dumps({"segments": [{"chapters": [3, 4], "summary": "新段"}]},
                              ensure_ascii=False)
        _mock_seg(monkeypatch, fake_post)

        r = pi.segment_chapters(test_db, "书", batch=2)
        assert len(called) == 1, "只应跑未完成的那一批"
        assert r["skipped_batches"] == 1 and r["batches_run"] == 1
        rows = _rows(test_db)
        assert [x.segment_no for x in rows] == [1, 1, 2, 2], "新批段号应从已有最大值续接"
        assert rows[0].segment_summary == "旧段", "已完成的批次不该被改写"

    def test_all_done_early_return(self, test_db, monkeypatch):
        _seed(test_db, [1, 2])
        test_db.query(pi.ChapterSummaryORM).update({"segment_no": 1})
        test_db.commit()

        def boom(k, c, **kw):
            raise AssertionError("不应发起任何请求")
        _mock_seg(monkeypatch, boom)
        r = pi.segment_chapters(test_db, "书", batch=2)
        assert r["batches_run"] == 0 and r["skipped_batches"] == 1

    def test_partial_batch_restarts_from_that_batch(self, test_db, monkeypatch):
        """批次只完成一半（有章无段号）→ 该批必须重算（前缀式跳过只认"整批完成"）。"""
        _seed(test_db, [1, 2, 3, 4])
        test_db.query(pi.ChapterSummaryORM).filter(
            pi.ChapterSummaryORM.chapter_no == 1
        ).update({"segment_no": 1}, synchronize_session=False)
        test_db.commit()
        called: list[str] = []

        def fake_post(k, c, **kw):
            called.append(c)
            return json.dumps({"segments": [
                {"chapters": [int(x) for x in _re.findall(r"第(\d+)章", c)],
                 "summary": "整批一段"}]}, ensure_ascii=False)
        _mock_seg(monkeypatch, fake_post)
        r = pi.segment_chapters(test_db, "书", batch=2)
        assert len(called) == 2 and r["skipped_batches"] == 0


class TestSegmentConcurrency:
    def test_concurrent_keeps_chapter_order(self, test_db, monkeypatch):
        """并发跑多批 → 段号仍严格按章节顺序分配。"""
        _seed(test_db, [1, 2, 3, 4, 5, 6])

        def fake_post(k, c, **kw):
            nos = [int(x) for x in _re.findall(r"第(\d+)章", c)]
            return json.dumps({"segments": [
                {"chapters": [no], "summary": f"段{no}"} for no in nos
            ]}, ensure_ascii=False)
        _mock_seg(monkeypatch, fake_post)

        r = pi.segment_chapters(test_db, "书", batch=2, concurrency=3)
        rows = _rows(test_db)
        assert [x.segment_no for x in rows] == [1, 2, 3, 4, 5, 6]
        assert r["segments"] == 6

    def test_batch_failure_does_not_break_others(self, test_db, monkeypatch):
        """某批失败 → 该批回退单段，其他批正常。"""
        _seed(test_db, [1, 2, 3, 4])
        state = {"n": 0}

        def flaky(k, c, **kw):
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("boom")
            nos = [int(x) for x in _re.findall(r"第(\d+)章", c)]
            return json.dumps({"segments": [
                {"chapters": [no], "summary": f"段{no}"} for no in nos
            ]}, ensure_ascii=False)
        _mock_seg(monkeypatch, flaky)

        r = pi.segment_chapters(test_db, "书", batch=2, concurrency=1)
        rows = _rows(test_db)
        assert all(x.segment_no is not None for x in rows)   # 全覆盖（失败批回退单段）
        assert r["segments"] == 3
