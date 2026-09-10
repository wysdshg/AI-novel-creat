"""SSE 生成链路核心件（B 方案：最易崩的第 1 处）。

覆盖 chapter.py 的三个纯逻辑件：
- _sse：SSE 帧格式（前端逐行解析的契约源头）
- _content_only_stream：正文流包装 + close() 时 GeneratorExit 确定性传播
  （当年 C2 坑：entity_suggestion 在 done 之后发 → 客户端已断开）
- _RepetitionGuard：双层复读检测（近窗重叠 + 句子级 3 次）
"""
import pytest

from app.routers.chapter import (
    _RepetitionGuard,
    _content_only_stream,
    _sse,
)


# ---------- _sse 帧格式 ----------

def test_sse_frame_exact_format():
    assert _sse("chunk", {"text": "雨落"}) == 'event: chunk\ndata: {"text": "雨落"}\n\n'


def test_sse_chinese_not_escaped():
    # ensure_ascii=False 是前端直读的契约：中文不允许变 \uXXXX
    frame = _sse("saved", {"chapter_id": "x1", "word_count": 3})
    assert "chapter_id" in frame and frame.endswith("\n\n")
    assert "\\u" not in frame


def test_sse_payload_roundtrip():
    import json
    payload = {"text": "他说：“三招。”", "n": 2}
    frame = _sse("chunk", payload)
    data_line = [l for l in frame.splitlines() if l.startswith("data: ")][0]
    assert json.loads(data_line[len("data: "):]) == payload


# ---------- _content_only_stream ----------

def test_content_only_stream_yields_tuples():
    gen = _content_only_stream(iter(["雨", "从县道", "斜插"]))
    assert list(gen) == [("content", "雨"), ("content", "从县道"), ("content", "斜插")]


def test_content_only_stream_empty_upstream():
    assert list(_content_only_stream(iter([]))) == []


def test_content_only_stream_close_propagates_to_upstream():
    # close() 必须立刻打断上游（RepetitionGuard 触发后靠这个停掉计费）
    closed = []

    def upstream():
        try:
            yield "a"
            yield "b"  # 不应被消费到
        finally:
            closed.append(True)

    gen = _content_only_stream(upstream())
    assert next(gen) == ("content", "a")
    gen.close()
    assert closed == [True]
    with pytest.raises(StopIteration):
        next(gen)


# ---------- _RepetitionGuard ----------

def _sentence(i):
    return f"第{i}回他沿着河边走了半里地看雾气漫过桥墩。"


def test_guard_normal_text_never_triggers():
    g = _RepetitionGuard()
    for i in range(25):
        assert g.feed(_sentence(i)) is True
    assert g.is_triggered is False


def test_guard_sentence_repeated_3_times_triggers():
    g = _RepetitionGuard()
    s = _sentence(0)
    assert g.feed(s) is True   # 第 1 次
    assert g.feed(s) is True   # 第 2 次
    assert g.feed(s) is False  # 第 3 次 → 截断
    assert g.is_triggered is True


def test_guard_short_sentence_repeat_is_neutral():
    # <12 字的短句是口癖/呼应，不参与复读判定
    g = _RepetitionGuard()
    for _ in range(6):
        assert g.feed("他冷笑。雨还在下。") is True
    assert g.is_triggered is False


def test_guard_after_triggered_stays_closed():
    g = _RepetitionGuard()
    s = _sentence(1)
    g.feed(s)
    g.feed(s)
    g.feed(s)
    assert g.is_triggered is True
    assert g.feed("全新的内容") is False  # 触发后恒 False，调用方必须断流


def test_guard_split_across_chunks_still_counts():
    # 同一句被 chunk 边界劈开也要数得出来（_pending 拼接逻辑）
    g = _RepetitionGuard()
    s = _sentence(2)
    half = len(s) // 2
    assert g.feed(s[:half]) is True
    assert g.feed(s[half:]) is True   # 第 1 次完整句
    assert g.feed(s) is True          # 第 2 次
    assert g.feed(s) is False         # 第 3 次
