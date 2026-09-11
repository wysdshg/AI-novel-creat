"""Phase 7.1 导入管线：切章 / 概括入库 / 段切分 / 分类（全部 mock LLM，不出网）。

覆盖重点：
- **幂等断点续跑**：已概括的章重跑自动跳过；失败章跳过不阻断，重跑自动补；
- **全覆盖兜底**：LLM 段切分漏标章节 → 归入最后一段；JSON 解析失败 → 整批回退单段；
- **写回正确性**：segment_no / segment_summary / plot_label 落到对应章节行。
"""
import json

from app.services import plot_import as pi


def _mk_book(tmp_path, chapters: dict[int, str]) -> str:
    book = tmp_path / "testbook"
    book.mkdir(exist_ok=True)
    for no, text in chapters.items():
        (book / f"{no:04d}_第{no}章测试.txt").write_text(text, encoding="utf-8")
    return str(book)


class TestDiscover:
    def test_parse_names_sorted(self, tmp_path):
        book = _mk_book(tmp_path, {12: "乙", 1: "甲", 3: "丙"})
        chs = pi.discover_chapters(book)
        assert [c["no"] for c in chs] == [1, 3, 12]
        assert chs[0]["title"] == "第1章测试"

    def test_empty_dir_raises_on_import(self, test_db, tmp_path, monkeypatch):
        empty = tmp_path / "empty"
        empty.mkdir()
        try:
            pi.import_chapters(test_db, str(empty), "书")
            raised = False
        except RuntimeError:
            raised = True
        assert raised, "空目录应报错而不是静默成功"


class TestImportChapters:
    def test_import_and_idempotent(self, test_db, tmp_path, monkeypatch):
        book = _mk_book(tmp_path, {1: "第一章正文甲甲甲", 2: "第二章正文乙乙乙"})
        outs = iter(["概括一", "概括二"])
        monkeypatch.setattr(pi, "sf_chat", lambda db, c, **kw: next(outs))
        st = pi.import_chapters(test_db, book, "测试书")
        assert st["done"] == 2 and st["skipped"] == 0 and st["failed"] == 0
        rows = test_db.query(pi.ChapterSummaryORM).order_by(
            pi.ChapterSummaryORM.chapter_no).all()
        assert rows[0].summary == "概括一" and rows[1].summary == "概括二"
        assert rows[0].title == "第1章测试"

        st2 = pi.import_chapters(test_db, book, "测试书")   # 幂等重跑
        assert st2["skipped"] == 2 and st2["done"] == 0

    def test_failed_chapter_skips_and_backfills(self, test_db, tmp_path, monkeypatch):
        book = _mk_book(tmp_path, {1: "甲甲甲", 2: "乙乙乙（第二章）", 3: "丙丙丙"})
        state = {"n": 0}

        def fake(db, c, **kw):
            state["n"] += 1
            if state["n"] == 2:      # 第二次调用（第 2 章）失败
                raise RuntimeError("boom")
            return "概括"
        monkeypatch.setattr(pi, "sf_chat", fake)
        st = pi.import_chapters(test_db, book, "书")
        assert st["done"] == 2 and st["failed"] == 1
        st2 = pi.import_chapters(test_db, book, "书")   # 重跑补失败章
        assert st2["done"] == 1 and st2["skipped"] == 2
        assert test_db.query(pi.ChapterSummaryORM).count() == 3

    def test_range_filter(self, test_db, tmp_path, monkeypatch):
        book = _mk_book(tmp_path, {i: f"正文{i}" for i in (1, 2, 3, 4)})
        monkeypatch.setattr(pi, "sf_chat", lambda db, c, **kw: "概")
        st = pi.import_chapters(test_db, book, "书", start=2, end=3)
        assert st["done"] == 2
        nos = [r.chapter_no for r in test_db.query(pi.ChapterSummaryORM).all()]
        assert sorted(nos) == [2, 3]


class TestSegment:
    def _seed(self, test_db, nos):
        for no in nos:
            test_db.add(pi.ChapterSummaryORM(
                id=f"s{no}", book_name="书", chapter_no=no, summary=f"第{no}章概括"))
        test_db.commit()

    def test_writeback(self, test_db, monkeypatch):
        self._seed(test_db, [1, 2, 3, 4])
        raw = json.dumps({"segments": [
            {"chapters": [1, 2], "summary": "段一概括"},
            {"chapters": [3, 4], "summary": "段二概括"},
        ]}, ensure_ascii=False)
        monkeypatch.setattr(pi, "sf_chat", lambda db, c, **kw: raw)
        r = pi.segment_chapters(test_db, "书", batch=10)
        assert r["segments"] == 2
        rows = test_db.query(pi.ChapterSummaryORM).order_by(
            pi.ChapterSummaryORM.chapter_no).all()
        assert [r.segment_no for r in rows] == [1, 1, 2, 2]
        assert rows[0].segment_summary == "段一概括"

    def test_uncovered_chapter_falls_back(self, test_db, monkeypatch):
        """LLM 漏标第 3 章 → 兜底归入最后一段（保证全覆盖）。"""
        self._seed(test_db, [1, 2, 3])
        raw = json.dumps({"segments": [{"chapters": [1, 2], "summary": "段一"}]},
                         ensure_ascii=False)
        monkeypatch.setattr(pi, "sf_chat", lambda db, c, **kw: raw)
        r = pi.segment_chapters(test_db, "书", batch=10)
        rows = test_db.query(pi.ChapterSummaryORM).order_by(
            pi.ChapterSummaryORM.chapter_no).all()
        assert rows[2].segment_no == 1
        assert r["segments"] == 1

    def test_bad_json_falls_back_single_segment(self, test_db, monkeypatch):
        self._seed(test_db, [1, 2])
        monkeypatch.setattr(pi, "sf_chat", lambda db, c, **kw: "这不是JSON")
        r = pi.segment_chapters(test_db, "书", batch=10)
        assert r["segments"] == 1
        rows = test_db.query(pi.ChapterSummaryORM).all()
        assert all(r.segment_no == 1 for r in rows)

    def test_reseg_clears_old(self, test_db, monkeypatch):
        """重算段前要清旧标记（否则旧 segment_no 残留产生交错）。"""
        self._seed(test_db, [1, 2])
        test_db.query(pi.ChapterSummaryORM).update({"segment_no": 9})
        test_db.commit()
        raw = json.dumps({"segments": [{"chapters": [1, 2], "summary": "新段"}]})
        monkeypatch.setattr(pi, "sf_chat", lambda db, c, **kw: raw)
        pi.segment_chapters(test_db, "书", batch=10)
        rows = test_db.query(pi.ChapterSummaryORM).all()
        assert all(r.segment_no == 1 for r in rows), "旧段号 9 应被清掉"


class TestLabel:
    def test_label_writeback(self, test_db, monkeypatch):
        test_db.add(pi.ChapterSummaryORM(id="a", book_name="书", chapter_no=1,
                                         summary="概", segment_no=1, segment_summary="段概"))
        test_db.add(pi.ChapterSummaryORM(id="b", book_name="书", chapter_no=2,
                                         summary="概", segment_no=1, segment_summary="段概"))
        test_db.commit()
        monkeypatch.setattr(pi, "sf_chat", lambda db, c, **kw: "学院大比")
        r = pi.label_segments(test_db, "书")
        assert r["labeled"] == 1 and r["segments"] == 1
        rows = test_db.query(pi.ChapterSummaryORM).all()
        assert all(r.plot_label == "学院大比" for r in rows)

    def test_label_failure_skips(self, test_db, monkeypatch):
        test_db.add(pi.ChapterSummaryORM(id="a", book_name="书", chapter_no=1,
                                         summary="概", segment_no=1, segment_summary="段概"))
        test_db.commit()

        def fake(db, c, **kw):
            raise RuntimeError("boom")
        monkeypatch.setattr(pi, "sf_chat", fake)
        r = pi.label_segments(test_db, "书")
        assert r["labeled"] == 0    # 失败跳过，不影响其他段
