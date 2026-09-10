"""级联删除（B 方案：最易崩的第 3 处，2026-09-09 e2e 三轮实测为 0 残留）。

用 test_db fixture（独立临时 SQLite）固化整链级联：
project → volume → article → chapter → 章级记忆（摄取生成）+ 角色库
+ 对话区 + 参考文档，删 project 后全部清空；同时验证删除只波及自己。

注：临时库没有模型配置，摄取走 fallback_extract 规则抽取（不走 LLM），
正好把「无模型可用」这条降级路径也一起测了。
"""
import pytest

from app.schemas.article import ArticleCreate
from app.schemas.chapter import ChapterCreate
from app.schemas.database import CharacterCreate
from app.schemas.volume import VolumeCreate


@pytest.fixture()
def populated_db(test_db):
    """建好一条完整数据链：project → volume → article → chapter(+摄取) → 角色/对话。"""
    from app.services import (
        article_crud, chapter_crud, character_crud, discussion_crud,
        ingestion, project_crud, volume_crud,
    )

    proj = project_crud.create_project(
        test_db, {"name": "级联测试作品", "genre": "测试", "summary": "s"})
    pid = proj["id"] if isinstance(proj, dict) else proj.id

    character_crud.create_character(
        test_db, pid, CharacterCreate(name="陈砚", role_type="主角"))
    discussion_crud.add_message(test_db, pid, "user", "下一章让主角出门")

    vol = volume_crud.create_volume(test_db, pid, VolumeCreate(name="卷一", summary=""))
    art = article_crud.create_article(
        test_db, pid, ArticleCreate(volume_id=vol.id, name="篇一", summary=""))
    ch = chapter_crud.create_chapter(
        test_db, pid,
        ChapterCreate(chapter_no=1, title="第一章", content="雨落在青石板上。" * 20,
                      word_count=140, article_id=art.id))
    # 触发写后摄取（fallback 路径）→ 章级记忆 + 参考文档摘要（级联面里最隐蔽的两张表）
    ingestion.ingest_chapter(test_db, pid, ch)
    test_db.commit()
    return pid


def _counts(test_db, pid):
    from app.models.orm import (
        ArticleORM, ChapterMemoryORM, ChapterORM, CharacterORM,
        DiscussionMessageORM, ReferenceDocORM, VolumeORM,
    )
    return {
        "volumes": test_db.query(VolumeORM).filter_by(project_id=pid).count(),
        "articles": test_db.query(ArticleORM).filter_by(project_id=pid).count(),
        "chapters": test_db.query(ChapterORM).filter_by(project_id=pid).count(),
        "memories": test_db.query(ChapterMemoryORM).filter_by(project_id=pid).count(),
        "characters": test_db.query(CharacterORM).filter_by(project_id=pid).count(),
        "discussion": test_db.query(DiscussionMessageORM).filter_by(project_id=pid).count(),
        "reference_docs": test_db.query(ReferenceDocORM).filter_by(project_id=pid).count(),
    }


def test_populated_chain_exists(populated_db, test_db):
    counts = _counts(test_db, populated_db)
    assert counts["volumes"] == 1
    assert counts["articles"] == 1
    assert counts["chapters"] == 1
    # 摄取产物：章级记忆至少 1 条；参考文档≥1（章摘要，fallback 路径也落库）
    assert counts["memories"] >= 1
    assert counts["reference_docs"] >= 1
    assert counts["characters"] == 1
    assert counts["discussion"] == 1


def test_cascade_delete_clears_everything(populated_db, test_db):
    from app.services import project_crud
    from app.models.orm import ProjectORM

    pid = populated_db
    before = _counts(test_db, pid)
    assert sum(before.values()) >= 6  # 链是真的存在过

    assert project_crud.delete_project(test_db, pid) is True
    test_db.commit()

    after = _counts(test_db, pid)
    assert all(v == 0 for v in after.values()), f"残留: {after}"
    assert test_db.query(ProjectORM).filter_by(id=pid).count() == 0


def test_delete_is_scoped_to_one_project(test_db):
    from app.services import project_crud
    from app.models.orm import ProjectORM

    p1 = project_crud.create_project(test_db, {"name": "甲", "genre": "g", "summary": ""})
    p2 = project_crud.create_project(test_db, {"name": "乙", "genre": "g", "summary": ""})
    id1 = p1["id"] if isinstance(p1, dict) else p1.id
    id2 = p2["id"] if isinstance(p2, dict) else p2.id

    project_crud.delete_project(test_db, id1)
    test_db.commit()

    assert test_db.query(ProjectORM).filter_by(id=id1).count() == 0
    assert test_db.query(ProjectORM).filter_by(id=id2).count() == 1


def test_delete_missing_project_returns_false(test_db):
    from app.services import project_crud
    assert project_crud.delete_project(test_db, "nonexistent-id") is False
