"""问题 1.2 回归：错误/占位提示绝不能落库成小说正文。

背景（2026-09-10 复核为活 bug）：`chapter.py` 把模型失败提示
`[模型调用失败，已降级为占位：…]` 与未配置模型的占位符直接 append 进
`content_parts`，随后 `full` 整体落库 —— 错误文案变成了小说正文；
走「重新生成」路径时更会把已有章节正文**静默覆盖**（数据丢失）。
修复：错误提示只进 `error_notes`（仅推前端展示），落库前用 `_can_persist` 判定。
"""
import pytest

from app.routers.chapter import _can_persist


def test_normal_content_can_persist():
    ok, reason = _can_persist("石阶尽头，云雾翻涌。", [])
    assert ok is True
    assert reason == ""


def test_blank_content_blocked():
    for blank in ("", "   ", "\n\n\t"):
        ok, reason = _can_persist(blank, [])
        assert ok is False, f"{blank!r} 不应落库"
        assert reason == "模型未返回任何正文"


def test_none_content_blocked():
    ok, reason = _can_persist(None, [])
    assert ok is False
    assert reason == "模型未返回任何正文"


def test_error_note_surfaced_as_reason():
    note = "[模型调用失败，已降级为占位：ConnectionError: timeout]"
    ok, reason = _can_persist("", [note])
    assert ok is False
    assert reason == note


def test_multiple_error_notes_joined():
    ok, reason = _can_persist("   ", ["错误A", "错误B"])
    assert ok is False
    assert reason == "错误A；错误B"


def test_empty_notes_ignored_in_reason():
    ok, reason = _can_persist("", ["", "   ", ""])
    assert ok is False
    assert reason == "模型未返回任何正文"


def test_notes_do_not_block_real_content():
    """即便本轮也出现过错，只要产出了真实正文就可落库（该提示不在 full 里）。"""
    ok, _ = _can_persist("沈砚按住胸口。", ["[模型调用失败…]"])
    assert ok is True


def test_reason_never_contains_placeholder_as_content():
    """占位符只能作为"原因"返回，不能被当作可落库正文。"""
    placeholder = "[章节正文占位 — 未配置可用模型，请在「模型配置」中添加并设为默认]"
    ok, reason = _can_persist("", [placeholder])
    assert ok is False
    assert reason == placeholder
