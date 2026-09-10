"""向量存储与编排层单测（A1+A2）。

不调真实 API：向量直接构造正交基，验证存储/检索协议语义。
双实现（SqliteVecStore / BruteVectorStore）在 test_db 上跑同一组用例，
保证「底座可换、行为不变」的契约成立。
"""
import uuid

import pytest

from app.services.vector_store import (
    BruteVectorStore, SqliteVecStore, VectorRow, get_store, vec_index_available,
)
from app.models.orm import VectorChunkORM
from app.services.vector_index import _chunk_text
from app.services.embedding_client import _l2_normalize


def _row(chunk_id, vec, sid="src-1", cidx=0, pid="p1", stype="ref_doc", text=""):
    return VectorRow(chunk_id=chunk_id, project_id=pid, source_type=stype,
                     source_id=sid, chunk_idx=cidx, chunk_text=text or f"chunk {cidx}",
                     model="mock", vector=vec)


def _basis(i, dim=1024):
    """第 i 维单位向量（已归一化的正交基）。"""
    v = [0.0] * dim
    v[i % dim] = 1.0
    return v


IMPLS = [BruteVectorStore]
if pytest.__version__:
    pass  # sqlite-vec 可用性在 fixture 里探测


@pytest.fixture()
def impls(test_db):
    """双实现列表：sqlite-vec 可用时包含 SqliteVecStore。"""
    out = [("brute", BruteVectorStore())]
    if vec_index_available(test_db):
        out.append(("sqlitevec", SqliteVecStore()))
    return out


@pytest.mark.parametrize("impl_idx", [0, 1])
def test_upsert_and_search_top1(test_db, impls, impl_idx):
    name, store = impls[impl_idx]
    if name == "sqlitevec" and not vec_index_available(test_db):
        pytest.skip("vec_index 不可用")
    rows = [
        _row("c0", _basis(0), text="主角在破庙躲雨"),
        _row("c1", _basis(1), text="反派夜袭宗门"),
        _row("c2", _basis(2), text="神器出世风波"),
    ]
    store.upsert(test_db, rows)
    test_db.commit()

    hits = store.search(test_db, "p1", "ref_doc", _basis(1), top_k=2)
    assert hits and hits[0].chunk_id == "c1", f"[{name}] 应命中 c1: {hits}"
    assert hits[0].score > hits[-1].score or len(hits) == 1


def test_search_scoped_by_project_and_source(test_db, impls):
    _, store = impls[0]
    store.upsert(test_db, [
        _row("p0a", _basis(0), pid="projA"),
        _row("p1a", _basis(0), pid="projB"),   # 别的作品
        _row("p0m", _basis(0), pid="projA", stype="chapter_memory"),  # 别的来源
    ])
    test_db.commit()
    hits = store.search(test_db, "projA", "ref_doc", _basis(0), top_k=10)
    assert [h.chunk_id for h in hits] == ["p0a"], "必须按 project+source 双重过滤"


def test_upsert_same_chunk_id_is_idempotent(test_db, impls):
    _, store = impls[0]
    store.upsert(test_db, [_row("dup", _basis(0))])
    store.upsert(test_db, [_row("dup", _basis(0))])
    test_db.commit()
    assert store.count(test_db, "p1") == 1, "同 chunk_id 重复 upsert 不得产生重复行"


def test_delete_by_source_removes_all_chunks(test_db, impls):
    _, store = impls[0]
    store.upsert(test_db, [
        _row("d1", _basis(0), sid="doc-1", cidx=0),
        _row("d2", _basis(1), sid="doc-1", cidx=1),
        _row("d3", _basis(2), sid="doc-2", cidx=0),
    ])
    test_db.commit()
    n = store.delete_by_source(test_db, "p1", "ref_doc", "doc-1")
    test_db.commit()
    assert n == 2
    assert store.count(test_db, "p1") == 1
    hits = store.search(test_db, "p1", "ref_doc", _basis(0), top_k=10)
    assert all(h.chunk_id != "d1" and h.chunk_id != "d2" for h in hits)


def test_both_impls_agree_on_ranking(test_db, impls):
    """双实现契约：同一组数据、同一查询，top-1 必须一致。"""
    if len(impls) < 2:
        pytest.skip("vec_index 不可用，无双实现可比")
    rows = [
        _row("r0", _basis(0), text="aaa"),
        _row("r1", _basis(1), text="bbb"),
        _row("r2", _basis(2), text="ccc"),
    ]
    for _, s in impls:
        s.upsert(test_db, rows)
    test_db.commit()
    q = [0.3, 0.9] + [0.0] * 1022  # 偏向维度 1
    tops = []
    for name, s in impls:
        hits = s.search(test_db, "p1", "ref_doc", q, top_k=1)
        tops.append((name, hits[0].chunk_id if hits else None))
    assert tops[0][1] == tops[1][1], f"双实现 top-1 不一致: {tops}"


# ---------- embedding_client 纯函数 ----------

def test_l2_normalize_keeps_direction_and_unit_length():
    v = _l2_normalize([3.0, 4.0])
    assert abs(sum(x * x for x in v) - 1.0) < 1e-12
    assert abs(v[0] - 0.6) < 1e-12 and abs(v[1] - 0.8) < 1e-12


def test_get_api_key_missing_returns_empty(test_db, monkeypatch):
    monkeypatch.delenv("NA_SILICONFLOW_KEY", raising=False)
    from app.services import embedding_client
    assert embedding_client.get_api_key(test_db) == ""


def test_get_api_key_env_first(test_db, monkeypatch):
    monkeypatch.setenv("NA_SILICONFLOW_KEY", "env-key")
    from app.services import embedding_client
    assert embedding_client.get_api_key(test_db) == "env-key"


# ---------- 切块 ----------

def test_chunk_text_short_passthrough():
    assert _chunk_text("短文本") == ["短文本"]
    assert _chunk_text("") == []


def test_chunk_text_paragraph_boundary():
    paras = [f"第{i}段内容。" * 20 for i in range(6)]  # 每段 120 字，共 720 字
    text = "\n\n".join(paras)
    chunks = _chunk_text(text)
    assert all(len(c) <= 500 for c in chunks)
    assert "".join(chunks).replace("\n\n", "") == text.replace("\n\n", "")
    assert len(chunks) >= 2


def test_chunk_text_oversized_paragraph_hard_split():
    huge = "字" * 1200
    chunks = _chunk_text(huge)
    assert all(len(c) <= 500 for c in chunks)
    assert sum(len(c) for c in chunks) == 1200


# ---------------- 全局表元数据过滤（2026-09-10 实测缺陷回归） ----------------

def test_search_is_project_scoped_even_with_huge_other_project(test_db, impls):
    """vec_index 是全局表：另一个项目塞入大量块后，本项目检索仍必须完整召回。

    回归自 e2e 实测缺陷——旧实现 k=top_k*3 全局过采样，被全局池 133 块挤占，
    本项目 4 份资料只召回 1 份。修复 = 辅助列元数据过滤（sqlite-vec v0.1.9）。
    """
    for impl_name, st in impls:
        # 干扰项目：200 个与查询同向的块
        noisy = [_row(f"noise-{i}", _basis(3), sid=f"n{i}", pid="other", text=f"干扰{i}")
                 for i in range(200)]
        st.upsert(test_db, noisy)
        # 本项目：3 个块，方向各异
        mine = [
            _row("m0", _basis(3), sid="d0", pid="p1", text="本项目-与查询同向"),
            _row("m1", _basis(4), sid="d1", pid="p1", text="本项目-次相关"),
            _row("m2", _basis(5), sid="d2", pid="p1", text="本项目-再次"),
        ]
        st.upsert(test_db, mine)
        test_db.commit()

        hits = st.search(test_db, "p1", "ref_doc", _basis(3), top_k=3)
        sids = {h.source_id for h in hits}
        assert sids == {"d0", "d1", "d2"}, f"[{impl_name}] 本项目应完整召回 3 块，实得 {hits}"
        assert all(h.chunk_id.startswith("m") for h in hits), f"[{impl_name}] 不得混入他项目块"
        # 清理，避免影响下一个实现
        st.delete_by_source(test_db, "other", "ref_doc", "n0")
        for i in range(200):
            st.delete_by_source(test_db, "other", "ref_doc", f"n{i}")
        for d in ("d0", "d1", "d2"):
            st.delete_by_source(test_db, "p1", "ref_doc", d)
        test_db.commit()


def test_rebuild_vec_index_from_orm(test_db):
    """vec_index 可丢弃重建：清空虚拟表后 rebuild 应完整回填。"""
    from app.services.vector_store import rebuild_vec_index, VEC_TABLE
    store = BruteVectorStore()
    store.upsert(test_db, [_row("r0", _basis(0)), _row("r1", _basis(1))])
    test_db.commit()
    test_db.connection().exec_driver_sql(f"DELETE FROM {VEC_TABLE}")
    n = rebuild_vec_index(test_db)
    test_db.commit()
    assert n == 2
    cnt = test_db.connection().exec_driver_sql(
        f"SELECT COUNT(*) FROM {VEC_TABLE}").scalar()
    assert cnt == 2


def test_remove_project_index_clears_both_tables(test_db):
    """作品级联删除：ORM 主表 + vec_index 虚拟表都要清干净。"""
    from app.services.vector_store import remove_project_index, VEC_TABLE
    store = get_store(test_db)
    store.upsert(test_db, [_row("x0", _basis(0), pid="px"), _row("x1", _basis(1), pid="px")])
    store.upsert(test_db, [_row("y0", _basis(2), pid="py")])
    test_db.commit()

    n = remove_project_index(test_db, "px")
    test_db.commit()
    assert n == 2
    assert test_db.query(VectorChunkORM).filter_by(project_id="px").count() == 0
    assert test_db.query(VectorChunkORM).filter_by(project_id="py").count() == 1
    if vec_index_available(test_db):
        left = test_db.connection().exec_driver_sql(
            f"SELECT chunk_id FROM {VEC_TABLE}").fetchall()
        assert [r[0] for r in left] == ["y0"]


# ---------------- 异步摄取 vs 删除作品的竞态（2026-09-10 e2e 实测） ----------------

def test_index_chunks_skips_when_project_deleted(test_db, monkeypatch):
    """作品已删除时不得再写向量（否则孤儿块永久挤占全局 vec_index 的 KNN 名额）。"""
    from app.services import vector_index
    from app.services.reference_crud import GLOBAL_PROJECT_ID

    called = []
    monkeypatch.setattr(vector_index.embedding_client, "embed_texts",
                        lambda texts, **kw: called.append(texts) or [[0.0] * 1024] * len(texts))

    # 不存在的项目 → 跳过，连 embedding 都不该调（省一次 API）
    n = vector_index.index_chunks(test_db, "no-such-project", "ref_doc", "d1", ["内容"])
    assert n == 0
    assert called == []

    # 全局资料池是虚拟 project_id（无 projects 行）→ 必须放行
    n2 = vector_index.index_chunks(test_db, GLOBAL_PROJECT_ID, "ref_doc", "d2", ["内容"])
    assert n2 == 1
    assert len(called) == 1


# ---------------- 异步摄取 vs 删除作品的竞态（2026-09-10 e2e 实测） ----------------

def test_index_chunks_skips_when_project_deleted(test_db, monkeypatch):
    """作品已删除时不得再写向量（否则孤儿块永久挤占全局 vec_index 的 KNN 名额）。"""
    from app.services import vector_index
    from app.services.reference_crud import GLOBAL_PROJECT_ID

    called = []
    monkeypatch.setattr(vector_index.embedding_client, "embed_texts",
                        lambda texts, **kw: called.append(texts) or [[0.0] * 1024] * len(texts))

    # 不存在的项目 → 跳过，连 embedding 都不该调（省一次 API）
    n = vector_index.index_chunks(test_db, "no-such-project", "ref_doc", "d1", ["内容"])
    assert n == 0
    assert called == []

    # 全局资料池是虚拟 project_id（无 projects 行）→ 必须放行
    n2 = vector_index.index_chunks(test_db, GLOBAL_PROJECT_ID, "ref_doc", "d2", ["内容"])
    assert n2 == 1
    assert len(called) == 1
