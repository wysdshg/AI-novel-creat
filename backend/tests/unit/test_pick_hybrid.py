"""A3 混合检索（关键词 + 向量 RRF 融合）单测。

向量通道全部 mock（search_similar / index_reference_doc），不触网、不依赖 key。
关键契约：
- 向量通道为空（未配 key / 无索引）时，行为与纯关键词版完全一致（向后兼容）；
- 向量独有命中的文档能被选出——这是融合的意义所在；
- 双通道命中的文档排名高于单通道命中的文档；
- 生命周期钩子：上传/导入建索引、删除清索引；
- reindex_project_references 对存量文档补建索引。
"""
import pytest

from app.services import vector_index
from app.services.vector_store import SearchHit
from app.schemas.reference import ReferenceDocCreate
from app.services.reference_crud import (
    pick_relevant,
    create_reference,
    delete_reference,
    import_global_references,
    GLOBAL_PROJECT_ID,
)


def _mk_doc(db, project_id, filename, content):
    return create_reference(db, project_id, ReferenceDocCreate(
        filename=filename, content_text=content, content_type="text/plain"))


QUERY = "陈默在破庙发现上古神器"


def _mk_kw_docs(db, pid):
    """A：标签/文件名直击 query（关键词第 1 名）；B：摘要 2-gram 部分命中（第 2 名）。"""
    a = _mk_doc(db, pid, "陈默神器.md", "关于陈默佩剑的设定。" + "补充" * 30)
    b = _mk_doc(db, pid, "配角设定.md", "陈默在破庙遇到配角，两人同行。" + "铺垫" * 30)
    return a, b


def test_no_vector_channel_matches_keyword_behavior(test_db):
    """未配 key（向量通道静默为空）→ 选中的应是关键词命中的文档，reason 含关键词。"""
    a, b = _mk_kw_docs(test_db, "p1")
    blocks, detail = pick_relevant(test_db, "p1", None, QUERY, top_k=2)
    ids = [d["id"] for d in detail if d["score"] is not None]
    assert a.id in ids
    # A 是关键词最强命中，应排在 B 前（或 B 因分>0 也入选但靠后）
    hit_a = next(d for d in detail if d["id"] == a.id)
    assert "关键词" in hit_a["channels"]


def test_vector_only_hit_gets_picked(test_db, monkeypatch):
    """关键词全 miss 的文档，靠向量通道命中也能入选（退保底行为被修正）。"""
    c = _mk_doc(test_db, "p1", "完全无关.md", "讲的是隔壁老王种菜。" + "种菜" * 30)
    hits = [SearchHit(chunk_id="ck1", source_type="ref_doc", source_id=c.id,
                      chunk_text="语义相关内容", score=0.83)]
    monkeypatch.setattr(vector_index, "search_similar", lambda *a, **k: hits)
    blocks, detail = pick_relevant(test_db, "p1", None, QUERY, top_k=2)
    hit_c = next((d for d in detail if d["id"] == c.id), None)
    assert hit_c is not None, "向量独有命中应被选出"
    assert "向量" in hit_c["channels"]
    assert hit_c["vec_score"] > 0.8


def test_dual_channel_outranks_single(test_db, monkeypatch):
    """双通道命中（B）RRF 分应高于仅关键词第 1 名（A）。"""
    a, b = _mk_kw_docs(test_db, "p1")
    # 向量通道只命中 B，且排第 1
    hits = [SearchHit(chunk_id="cb", source_type="ref_doc", source_id=b.id,
                      chunk_text="x", score=0.9)]
    monkeypatch.setattr(vector_index, "search_similar", lambda *a, **k: hits)
    blocks, detail = pick_relevant(test_db, "p1", None, QUERY, top_k=2)
    optional_hits = [d for d in detail if d["score"] is not None]
    assert optional_hits[0]["id"] == b.id, "双通道 B 应排在仅关键词 A 之前"
    assert set(optional_hits[0]["channels"]) == {"关键词", "向量"}
    assert optional_hits[0]["score"] > next(
        d["score"] for d in optional_hits if d["id"] == a.id)


def test_fallback_earliest_when_both_channels_empty(test_db):
    """双通道全空 → 保持旧行为：退回最早上传的一份保底。"""
    d1 = _mk_doc(test_db, "p1", "甲.md", "内容一" * 50)
    _mk_doc(test_db, "p2", "乙.md", "内容二" * 50)  # 别的项目，不应干扰
    blocks, detail = pick_relevant(test_db, "p1", None, "八竿子打不着的查询词", top_k=2)
    optional_hits = [d for d in detail if d["score"] is not None]
    assert [d["id"] for d in optional_hits] == [d1.id]
    assert optional_hits[0]["channels"] == ["保底"]


def test_must_digest_stays_on_top(test_db, monkeypatch):
    """篇章摘要（source=auto）置顶必备，不参与 RRF 竞争。"""
    _mk_kw_docs(test_db, "p1")
    digest_doc = _mk_doc(test_db, "p1", "篇章参考.md", "第一章摘要")
    from app.models.orm import ReferenceDocORM
    row = test_db.query(ReferenceDocORM).filter_by(id=digest_doc.id).first()
    row.source = "auto"
    test_db.commit()
    hits = [SearchHit(chunk_id="x", source_type="ref_doc", source_id=digest_doc.id,
                      chunk_text="x", score=0.99)]
    monkeypatch.setattr(vector_index, "search_similar", lambda *a, **k: hits)
    blocks, detail = pick_relevant(test_db, "p1", None, QUERY, top_k=2)
    assert detail[0]["id"] == digest_doc.id
    assert detail[0]["reason"] == "本篇剧情摘要（必备）"


def test_lifecycle_create_indexes_and_delete_removes(test_db, monkeypatch):
    """上传触发建索引；删除触发清索引。"""
    indexed, removed = [], []
    monkeypatch.setattr(vector_index, "index_reference_doc",
                        lambda db, doc: indexed.append(doc.id) or 1)
    monkeypatch.setattr(vector_index, "remove_reference_doc",
                        lambda db, doc: removed.append(doc.id) or 1)
    doc = _mk_doc(test_db, "p1", "钩子测试.md", "内容" * 20)
    assert indexed == [doc.id]
    assert delete_reference(test_db, "p1", doc.id) is True
    assert removed == [doc.id]


def test_import_global_references_indexes_copies(test_db, monkeypatch):
    """从全局池导入 → 每个副本触发一次建索引。"""
    g = _mk_doc(test_db, GLOBAL_PROJECT_ID, "全局资料.md", "全局内容" * 20)
    indexed = []
    monkeypatch.setattr(vector_index, "index_reference_doc",
                        lambda db, doc: indexed.append(doc.id) or 1)
    n = import_global_references(test_db, "p1", [g.id])
    assert n == 1
    assert len(indexed) == 1 and indexed[0] != g.id  # 是副本的新 id


def test_reindex_project_references_counts(test_db, monkeypatch):
    """存量补建：计数正确、幂等不报错。"""
    _mk_kw_docs(test_db, "p1")
    calls = []
    monkeypatch.setattr(vector_index, "index_reference_doc",
                        lambda db, doc: calls.append(doc.id) or 3)
    stats = vector_index.reindex_project_references(test_db, "p1")
    assert stats == {"docs": 2, "chunks": 6}
    assert len(calls) == 2
    # 再跑一遍幂等
    stats2 = vector_index.reindex_project_references(test_db, "p1")
    assert stats2 == {"docs": 2, "chunks": 6}
