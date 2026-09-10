"""问题 1.2 端到端回归：模型调用失败时，错误提示绝不落库成正文。

与 `test_chapter_persist_guard.py` 的分工：那个测纯函数 `_can_persist` 的判定逻辑；
本文件**真实驱动 SSE 生成器**（直接调路由函数 + 消费 body_iterator），
用「会抛异常的假适配器」复现模型失败，断言：

- 发出 `error` 事件（说明原因），且**不发 `saved`**；
- 新建章场景：**不创建**任何章节（不会留下一条内容是错误提示的脏数据）；
- 重新生成场景：**原有正文保持不变**（修复前会被错误提示覆盖 = 静默数据丢失）。

全程离线，不碰网络与真实模型。
"""
import json
import uuid

import pytest

from app.models.orm import (
    ModelConfigORM, ProjectORM, VolumeORM, ArticleORM, ChapterORM,
)
from app.routers import chapter as chapter_router
from app.schemas.chapter import GenerateRequest


class _BoomAdapter:
    """stream() 一调用就抛异常，复现「模型调用失败」。"""

    def __init__(self, *_a, **_kw):
        pass

    def stream(self, *_a, **_kw):
        raise RuntimeError("模拟上游连接失败")

    def chat(self, *_a, **_kw):
        raise RuntimeError("模拟上游连接失败")


def _seed_project(test_db):
    pid = uuid.uuid4().hex
    test_db.add(ProjectORM(id=pid, name="1.2回归", genre="测试"))
    vid = uuid.uuid4().hex
    test_db.add(VolumeORM(id=vid, project_id=pid, name="第一卷"))
    aid = uuid.uuid4().hex
    test_db.add(ArticleORM(id=aid, project_id=pid, name="第一篇", volume_id=vid))
    test_db.add(ModelConfigORM(
        id=uuid.uuid4().hex, name="假模型", vendor="openai_compat",
        api_base="http://127.0.0.1:1/v1", api_key="sk-test",
        model_name="fake", is_default=True, status="active",
    ))
    test_db.commit()
    return pid, aid


def _consume(resp):
    """把 StreamingResponse 的 SSE 流解析成 [(event, payload)]。

    Starlette 会把同步生成器包成 async 迭代器（iterate_in_threadpool），
    故用 asyncio 驱动（同步测试里跑一次事件循环即可）。
    """
    import asyncio

    async def _drain():
        chunks = []
        async for raw in resp.body_iterator:
            chunks.append(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        return "".join(chunks)

    text = asyncio.run(_drain())
    events = []
    for block in text.split("\n\n"):
        event, buf = None, ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                buf += line[len("data:"):].strip()
        if event:
            try:
                events.append((event, json.loads(buf) if buf else {}))
            except json.JSONDecodeError:
                events.append((event, {}))
    return events


@pytest.fixture()
def fake_failure(monkeypatch):
    """让章节生成拿到「必定失败」的适配器。"""
    monkeypatch.setattr(chapter_router, "get_adapter", lambda *a, **k: _BoomAdapter())


def test_failed_generation_does_not_create_chapter(test_db, fake_failure):
    """模型失败 + 新建章 → 不创建章节、不发 saved、发 error。"""
    pid, aid = _seed_project(test_db)
    before = test_db.query(ChapterORM).filter_by(project_id=pid).count()

    body = GenerateRequest(chapter_no=1, article_id=aid, title="第1章 测试",
                           from_discussion=False)
    resp = chapter_router.generate_chapter(pid, body, test_db)
    events = _consume(resp)
    names = [e for e, _ in events]

    assert "error" in names, f"应发 error 事件说明原因，实得 {names}"
    assert "saved" not in names, f"正文为空时不得落库，实得 {names}"
    err = dict(events)["error"]
    assert "模型调用失败" in err.get("message", "")

    after = test_db.query(ChapterORM).filter_by(project_id=pid).count()
    assert after == before, "不应创建任何章节（否则库里会多一条内容是错误提示的脏数据）"


def test_failed_regeneration_preserves_existing_content(test_db, fake_failure):
    """模型失败 + 重新生成已有章 → 原正文必须原样保留（修复前会被错误提示覆盖）。"""
    pid, aid = _seed_project(test_db)
    cid = uuid.uuid4().hex
    original = "石阶尽头，云雾翻涌。沈砚按住胸口。" * 5
    test_db.add(ChapterORM(id=cid, project_id=pid, article_id=aid, chapter_no=1,
                           title="第1章 原稿", content=original,
                           word_count=len(original)))
    test_db.commit()

    body = GenerateRequest(chapter_no=1, article_id=aid, chapter_id=cid,
                           title="第1章 原稿", from_discussion=False)
    resp = chapter_router.generate_chapter(pid, body, test_db)
    events = _consume(resp)
    names = [e for e, _ in events]

    assert "error" in names
    assert "saved" not in names, f"不得覆盖已有正文，实得 {names}"

    test_db.expire_all()
    row = test_db.query(ChapterORM).filter_by(id=cid).first()
    assert row.content == original, "已有章节正文被改动了（数据丢失）"
    assert "模型调用失败" not in (row.content or ""), "错误提示不得进入正文"
