"""Phase 3.2 回归：`_stream_two_phase` 合并后行为与改造前一致。

背景：`/discussion/chat` 与 `/discussion/global-chat` 各有一份约 80 行的两阶段
LOAD_REFS 流式逻辑，Phase 3.2 合并为 `_stream_two_phase`。合并的风险是
「两个入口行为悄悄分叉」，故本文件用**假适配器**直接驱动该生成器，锁死四条分支：

1. **短路**：Pass1 直接作答（无 LOAD_REFS）→ 只发 chunk，不调 stream；
2. **两阶段**：Pass1 请求 LOAD_REFS → 发 refs 事件 → 流式产出正文；
3. **Pass1 失败**：adapter.chat 抛异常 → 降级单次流式；
4. **无 chat 能力**：adapter 无 chat → 直接单次流式。

外加：观测增量 dict 的字段正确性（供 discussion_load_logs 落库）。
"""
import pytest

from app.routers import discussion


class FakeAdapter:
    """可编程假适配器：按脚本返回 Pass1 文本 / 流式分片。"""

    def __init__(self, pass1_text="", chunks=None, chat_raises=False, has_chat=True,
                 thinking_chunks=None):
        self.pass1_text = pass1_text
        self.chunks = chunks or []
        self.chat_raises = chat_raises
        self.thinking_chunks = thinking_chunks or []
        self.chat_calls = []
        self.stream_calls = 0
        self.has_chat = has_chat

    def chat(self, messages, temperature=None, enable_thinking=None):
        # 用实例属性模拟「适配器不支持 Pass1」——生成器用 hasattr 判断，
        # 故 has_chat=False 时抛 AttributeError 与之等效。
        if not self.has_chat:
            raise AttributeError("chat")
        self.chat_calls.append({"temperature": temperature, "enable_thinking": enable_thinking})
        if self.chat_raises:
            raise RuntimeError("pass1 boom")
        return self.pass1_text

    def stream(self, messages, temperature=None, enable_thinking=None):
        self.stream_calls += 1
        for c in self.chunks:
            yield c

    def stream_thinking(self, messages, temperature=None, enable_thinking=None):
        for t in self.thinking_chunks:
            yield t


def _drain(adapter, messages=None, want_thinking=False, monkeypatch=None,
           refs=None, settings=None):
    """跑一遍 `_stream_two_phase`，返回 (事件列表, assistant_text, assistant_thinking, obs)。

    参考/设定取数走 `reference_crud`，这里打桩避免碰 DB。
    """
    from app.services import reference_crud as ref_svc

    monkeypatch.setattr(ref_svc, "fetch_refs_by_ids", lambda db, ids: refs or [])
    monkeypatch.setattr(ref_svc, "fetch_settings_by_ids", lambda db, ids: settings or [])

    # 生成器内部会自建 SessionLocal 取参考；打桩成返回假对象即可
    monkeypatch.setattr(discussion._db, "SessionLocal", lambda: _FakeSession())

    msgs = messages if messages is not None else [{"role": "user", "content": "hi"}]
    a_text, a_think = [], []
    events = list(discussion._stream_two_phase(
        adapter, msgs,
        want_thinking=want_thinking, temperature=0.7, tag="test",
        assistant_text=a_text, assistant_thinking=a_think,
    ))
    return events, a_text, a_think, msgs


class _FakeSession:
    def close(self):
        pass


def _event_names(events):
    return [e.split("\n", 1)[0].replace("event: ", "") for e in events]


# ---------------- 分支 1：短路（Pass1 即最终回答）----------------
def test_short_circuit_single_call(monkeypatch):
    ad = FakeAdapter(pass1_text="直接回答，无需资料。")
    events, a_text, _, _ = _drain(ad, monkeypatch=monkeypatch)

    assert _event_names(events) == ["chunk"], "短路应只发一个 chunk 事件"
    assert ad.stream_calls == 0, "短路时不应调用流式接口"
    assert a_text == ["直接回答，无需资料。"]


def test_short_circuit_skips_when_first_text_empty(monkeypatch):
    """Pass1 返回空串（非异常）→ 走降级单次流式。"""
    ad = FakeAdapter(pass1_text="", chunks=["降级正文"])
    events, a_text, _, _ = _drain(ad, monkeypatch=monkeypatch)

    assert _event_names(events) == ["chunk"]
    assert ad.stream_calls == 1
    assert a_text == ["降级正文"]


# ---------------- 分支 2：两阶段加载 ----------------
def test_two_phase_emits_refs_then_chunks(monkeypatch):
    """Pass1 请求 LOAD_REFS → refs 事件 + 正文流。"""
    ad = FakeAdapter(pass1_text="LOAD_REFS:aa11", chunks=["正", "文"])
    events, a_text, _, msgs = _drain(
        ad, monkeypatch=monkeypatch, refs=[("参考甲.md", "内容甲")]
    )

    names = _event_names(events)
    assert names[0] == "refs", f"首个事件应为 refs，实际 {names}"
    assert names[1:] == ["chunk", "chunk"]
    assert a_text == ["正", "文"]
    # 参考正文应被注入 messages
    assert any("内容甲" in m.get("content", "") for m in msgs)


def test_two_phase_includes_settings(monkeypatch):
    """LOAD_SETTING 同样触发加载，且 refs 事件含设定名。"""
    import json
    ad = FakeAdapter(pass1_text="LOAD_SETTING:bb22", chunks=["答"])
    events, _, _, _ = _drain(
        ad, monkeypatch=monkeypatch, settings=[("官制体系", "详情内容")]
    )

    refs_evt = [e for e in events if e.startswith("event: refs")][0]
    payload = json.loads(refs_evt.split("data: ", 1)[1].split("\n")[0])
    assert payload["loaded"] == ["官制体系"]


def test_two_phase_invalid_ids_falls_back(monkeypatch):
    """选中 id 但取不到数据 → 注入「未加载」提示后直接作答（不死循环）。"""
    ad = FakeAdapter(pass1_text="LOAD_REFS:cc33", chunks=["兜底答"])
    events, a_text, _, msgs = _drain(ad, monkeypatch=monkeypatch, refs=[])

    names = _event_names(events)
    assert "refs" not in names, "取不到数据时不应发 refs 事件"
    assert names == ["chunk"]
    assert a_text == ["兜底答"]
    assert any("未能加载" in m.get("content", "") for m in msgs)


# ---------------- 分支 3：Pass1 异常降级 ----------------
def test_pass1_raises_degrades_to_stream(monkeypatch):
    ad = FakeAdapter(chat_raises=True, chunks=["降级"])
    events, a_text, _, _ = _drain(ad, monkeypatch=monkeypatch)

    assert _event_names(events) == ["chunk"]
    assert ad.stream_calls == 1
    assert a_text == ["降级"]


# ---------------- 分支 4：无 chat 能力 ----------------
def test_no_chat_capability(monkeypatch):
    ad = FakeAdapter(has_chat=False, chunks=["无pass1"])
    events, a_text, _, _ = _drain(ad, monkeypatch=monkeypatch)

    assert _event_names(events) == ["chunk"]
    assert ad.stream_calls == 1
    assert a_text == ["无pass1"]


# ---------------- 思考内容透传 ----------------
def test_thinking_chunks_collected_and_emitted(monkeypatch):
    ad = FakeAdapter(pass1_text="LOAD_REFS:dd44", chunks=["正文"],
                     thinking_chunks=["想1", "想2"])
    events, a_text, a_think, _ = _drain(
        ad, want_thinking=True, monkeypatch=monkeypatch, refs=[("f.md", "x")]
    )

    names = _event_names(events)
    assert names == ["refs", "thinking", "thinking", "chunk"]
    assert a_think == ["想1", "想2"], "思考内容需回传供持久化"
    assert a_text == ["正文"]


def test_no_thinking_when_disabled(monkeypatch):
    ad = FakeAdapter(pass1_text="LOAD_REFS:dd44", chunks=["正文"],
                     thinking_chunks=["不该出现"])
    events, _, a_think, _ = _drain(
        ad, want_thinking=False, monkeypatch=monkeypatch, refs=[("f.md", "x")]
    )
    assert a_think == []
    assert "thinking" not in _event_names(events)


# ---------------- LOAD_REFS 指令泄漏拦截 ----------------
def test_load_refs_marker_stripped_from_output(monkeypatch):
    """模型偶发在正文里漏出 LOAD_REFS 指令行，必须被剥掉。"""
    ad = FakeAdapter(pass1_text="LOAD_REFS:dd44", chunks=["LOAD_REFS:ee55\n真正的正文"])
    _, a_text, _, _ = _drain(ad, monkeypatch=monkeypatch, refs=[("f.md", "x")])
    joined = "".join(a_text)
    assert "LOAD_REFS" not in joined, f"指令泄漏: {joined!r}"
    assert "真正的正文" in joined


# ---------------- 观测增量 dict ----------------
def test_obs_payload_short_circuit(monkeypatch):
    ad = FakeAdapter(pass1_text="答案")
    _, _, _, _ = _drain(ad, monkeypatch=monkeypatch)
    # 无法直接拿返回值（被 yield 消费），故用生成器手动驱动取值
    from app.services import reference_crud as ref_svc
    monkeypatch.setattr(ref_svc, "fetch_refs_by_ids", lambda db, ids: [])
    monkeypatch.setattr(ref_svc, "fetch_settings_by_ids", lambda db, ids: [])
    monkeypatch.setattr(discussion._db, "SessionLocal", lambda: _FakeSession())

    gen = discussion._stream_two_phase(
        FakeAdapter(pass1_text="答案"), [{"role": "user", "content": "q"}],
        want_thinking=False, temperature=0.7, tag="t",
        assistant_text=[], assistant_thinking=[],
    )
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            assert stop.value == {"short_circuited": True}
            break


def test_obs_payload_two_phase(monkeypatch):
    from app.services import reference_crud as ref_svc
    monkeypatch.setattr(ref_svc, "fetch_refs_by_ids", lambda db, ids: [("a.md", "t")])
    monkeypatch.setattr(ref_svc, "fetch_settings_by_ids", lambda db, ids: [])
    monkeypatch.setattr(discussion._db, "SessionLocal", lambda: _FakeSession())

    gen = discussion._stream_two_phase(
        FakeAdapter(pass1_text="LOAD_REFS:ff66", chunks=["x"]),
        [{"role": "user", "content": "q"}],
        want_thinking=False, temperature=0.7, tag="t",
        assistant_text=[], assistant_thinking=[],
    )
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            assert stop.value["ref_loaded"] is True
            assert stop.value["load_ref_ids"] == ["ff66"]
            break


def test_obs_payload_pass1_failed(monkeypatch):
    from app.services import reference_crud as ref_svc
    monkeypatch.setattr(ref_svc, "fetch_refs_by_ids", lambda db, ids: [])
    monkeypatch.setattr(ref_svc, "fetch_settings_by_ids", lambda db, ids: [])
    monkeypatch.setattr(discussion._db, "SessionLocal", lambda: _FakeSession())

    gen = discussion._stream_two_phase(
        FakeAdapter(chat_raises=True, chunks=["x"]), [{"role": "user", "content": "q"}],
        want_thinking=False, temperature=0.7, tag="t",
        assistant_text=[], assistant_thinking=[],
    )
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            assert stop.value == {"pass1_failed": True}
            break
