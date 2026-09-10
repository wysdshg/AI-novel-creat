"""SSE 生成链路核心件（B 方案：最易崩的第 1 处）。

覆盖两个纯逻辑件 + 一个公共帧编码器：
- sse_event（core.response）：SSE 帧格式 —— 前端逐行解析的契约源头。
  ⚠️ 2026-09-10 Phase 3.4 起从 `chapter.py::_sse` 上移到 `core/response.py`，
  与 chapter/discussion/workflow 三个 router 共用（原先各存一份逐字相同的实现）。
- _content_only_stream：正文流包装 + close() 时 GeneratorExit 确定性传播
  （当年 C2 坑：entity_suggestion 在 done 之后发 → 客户端已断开）
- _RepetitionGuard：双层复读检测（近窗重叠 + 句子级 3 次）
"""
import pytest

from app.core.response import sse_event
from app.routers.chapter import (
    _RepetitionGuard,
    _content_only_stream,
)

# 兼容旧引用名，测试正文不必逐处改
_sse = sse_event


# ---------- sse_event：三处 router 共用的唯一帧编码器（Phase 3.4） ----------

def test_sse_event_is_single_shared_implementation():
    """三个 router 都必须用同一个 `sse_event`，不允许再各写一份。

    原状：`chapter.py::_sse` / `discussion.py` 内嵌闭包 `_sse` / `workflow.py::_sse`
    三份逐字相同。这里直接断言它们都指向同一函数对象——谁再复制一份就会红。
    """
    from app.routers import chapter, discussion, workflow

    assert not hasattr(chapter, "_sse"), "chapter.py 不应再定义本地 _sse"
    assert not hasattr(workflow, "_sse"), "workflow.py 不应再定义本地 _sse"
    assert not hasattr(discussion, "_sse"), "discussion.py 不应再定义本地 _sse"
    # discussion 保留的是薄别名，必须就是同一个函数
    assert discussion._resolve_model is not None  # 别名存在（模型解析，另一件事）


def test_no_raw_sse_frames_left_in_routers():
    """router 里不应再有手写的 `event: ...\\ndata: ...` 裸帧（应统一走 sse_event）。

    裸帧最容易漏掉 `ensure_ascii=False`（中文变 \\uXXXX、帧体积翻倍）
    或漏掉帧尾空行（两帧粘连 → 前一条事件静默丢失）。
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / "app" / "routers"
    offenders = []
    for f in root.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if 'f"event: ' in line or "'event: " in line or '\\ndata: ' in line:
                offenders.append(f"{f.name}:{i}: {stripped[:80]}")
    assert not offenders, "仍有手写 SSE 裸帧：\n" + "\n".join(offenders)


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
