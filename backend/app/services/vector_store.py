"""向量存储（A2）：协议 + 双实现，接口一步到位、底座可热插拔。

架构（2026-09-10 与用户对齐「一步到位」方案）：
- source of truth = `vector_chunks` 普通表（ORM，SQLAlchemy 管理，向量存 JSON）；
- 加速索引 = sqlite-vec 的 vec0 虚拟表 `vec_index`（L2 KNN），可随时重建；
- `SqliteVecStore`：vec_index 可用时的主实现（KNN 查询 + 回表过滤）；
- `BruteVectorStore`：扩展加载失败/虚拟表缺失时的自动回退（纯 Python 点积，
  无 numpy——1024 维 × 百级块毫秒级，性能完全够）；
- 业务代码（vector_index / 未来的 pick_relevant 融合）**只依赖 VectorStore
  协议**，未来换 sqlite-vec 新版本 / FAISS / 独立向量库 = 新增一个实现类 +
  工厂改一行，调用方零改动。

向量约定：全部 L2 归一化（embedding_client 已做，本模块防御性再归一），
归一化后 L2 距离与余弦相似度单调等价。事务：实现内不 commit，由调用方统一提交。
"""
import logging
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.models.orm import VectorChunkORM

VEC_TABLE = "vec_index"
EMBED_DIM = 1024


logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class VectorRow:
    """一条向量块（upsert 的输入）。"""

    chunk_id: str
    project_id: str
    source_type: str
    source_id: str
    chunk_idx: int
    chunk_text: str
    model: str
    vector: list[float]


@dataclass
class SearchHit:
    chunk_id: str
    source_type: str
    source_id: str
    chunk_text: str
    score: float  # 相似度（越大越相关）：brute=余弦，sqlite-vec=1/(1+L2)


def _upsert_rows_sql(db: Session, rows: list[VectorRow]) -> None:
    """写路径走 SQLite 原生 INSERT OR REPLACE（幂等由数据库保证）。

    不走 ORM unit-of-work：向量表是纯存储层（无关系导航），且实测同 session
    内对同主键先 merge 再 flush 会把多条 INSERT 一起下发触发唯一约束
    （2026-09-10 单测实抓）——原生 SQL 语义最清晰。
    """
    conn = db.connection()
    for r in rows:
        conn.exec_driver_sql(
            "INSERT OR REPLACE INTO vector_chunks "
            "(id, project_id, source_type, source_id, chunk_idx, chunk_text, "
            " model, dim, embedding_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r.chunk_id, r.project_id, r.source_type, r.source_id,
             r.chunk_idx, r.chunk_text, r.model, len(r.vector),
             json.dumps(r.vector), _now_iso()),
        )


def _delete_source_sql(db: Session, project_id: str, source_type: str, source_id: str) -> int:
    cur = db.connection().exec_driver_sql(
        "DELETE FROM vector_chunks WHERE project_id=? AND source_type=? AND source_id=?",
        (project_id, source_type, source_id),
    )
    return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


@runtime_checkable
class VectorStore(Protocol):
    """向量存储协议——业务代码只认这四个方法，全部收 db session。"""

    def upsert(self, db: Session, rows: list[VectorRow]) -> None: ...

    def delete_by_source(self, db: Session, project_id: str,
                         source_type: str, source_id: str) -> int: ...

    def search(self, db: Session, project_id: str, source_type: str,
               query_vec: list[float], top_k: int = 5) -> list[SearchHit]: ...

    def count(self, db: Session, project_id: str | None = None) -> int: ...


class BruteVectorStore:
    """纯 Python 余弦（无 numpy）。sqlite-vec 不可用时的自动回退实现。"""

    def upsert(self, db: Session, rows: list[VectorRow]) -> None:
        _upsert_rows_sql(db, rows)

    def delete_by_source(self, db: Session, project_id: str,
                         source_type: str, source_id: str) -> int:
        return _delete_source_sql(db, project_id, source_type, source_id)

    def search(self, db: Session, project_id: str, source_type: str,
               query_vec: list[float], top_k: int = 5) -> list[SearchHit]:
        qv = _l2_normalize(query_vec)
        hits: list[SearchHit] = []
        for row in db.query(VectorChunkORM).filter_by(
                project_id=project_id, source_type=source_type).all():
            try:
                v = json.loads(row.embedding_json or "[]")
            except Exception as e:  # noqa: BLE001
                # 单行向量损坏 → 跳过（不能因一行坏数据让整次检索空手而归），但要留痕（Phase 3.5）
                logger.warning(
                    f"[vector_store] 跳过向量损坏的块 id={str(row.id)[:8]}: {type(e).__name__}: {e}"
                )
                continue
            if len(v) != len(qv):
                continue
            dot = sum(a * b for a, b in zip(qv, v))
            hits.append(SearchHit(row.id, row.source_type, row.source_id,
                                  row.chunk_text, round(dot, 6)))
        hits.sort(key=lambda h: -h.score)
        return hits[:top_k]

    def count(self, db: Session, project_id: str | None = None) -> int:
        q = db.query(VectorChunkORM)
        if project_id:
            q = q.filter_by(project_id=project_id)
        return q.count()


class SqliteVecStore:
    """sqlite-vec vec0 KNN 主实现。vec_index 虚拟表由 init_db 创建。

    vec_index 只是加速索引：写路径先写 ORM（source of truth）再镜像进 vec_index；
    读路径 KNN 取 chunk_id 后回 ORM 表过滤 project/source——即使 vec_index
    与 ORM 出现不一致，最坏结果只是漏召回，可用 rebuild 重建修复。
    """

    def _sync_vec_index(self, db: Session, rows: list[VectorRow]) -> None:
        import sqlite_vec

        conn = db.connection()
        for r in rows:
            conn.exec_driver_sql(
                f"DELETE FROM {VEC_TABLE} WHERE chunk_id = ?", (r.chunk_id,))
            conn.exec_driver_sql(
                f"INSERT INTO {VEC_TABLE}(chunk_id, embedding, project_id, source_type) "
                "VALUES(?, ?, ?, ?)",
                (r.chunk_id, sqlite_vec.serialize_float32(_l2_normalize(r.vector)),
                 r.project_id, r.source_type),
            )

    def _remove_vec_index(self, db: Session, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        conn = db.connection()
        for cid in chunk_ids:
            conn.exec_driver_sql(
                f"DELETE FROM {VEC_TABLE} WHERE chunk_id = ?", (cid,))

    def upsert(self, db: Session, rows: list[VectorRow]) -> None:
        _upsert_rows_sql(db, rows)
        self._sync_vec_index(db, rows)

    def delete_by_source(self, db: Session, project_id: str,
                         source_type: str, source_id: str) -> int:
        # 先取要删的 chunk_id（vec_index 清理用），再删主表
        cur = db.connection().exec_driver_sql(
            "SELECT id FROM vector_chunks WHERE project_id=? AND source_type=? AND source_id=?",
            (project_id, source_type, source_id),
        )
        ids = [r[0] for r in cur.fetchall()]
        n = _delete_source_sql(db, project_id, source_type, source_id)
        self._remove_vec_index(db, ids)
        return n

    def search(self, db: Session, project_id: str, source_type: str,
               query_vec: list[float], top_k: int = 5) -> list[SearchHit]:
        import sqlite_vec

        qv = _l2_normalize(query_vec)
        conn = db.connection()
        # ⚠️ vec_index 是**全局表**（所有作品 + 全局资料池共用），KNN 必须先按
        # project_id/source_type 过滤再取 k——否则全局池的块会挤占 top-k，
        # 回表过滤后本项目块几乎全被截掉（2026-09-10 实测：4 份本项目资料只召回 1 份）。
        # sqlite-vec v0.1.9 支持辅助列元数据过滤，故 project_id/source_type 存为辅助列。
        cur = conn.exec_driver_sql(
            f"SELECT chunk_id, distance FROM {VEC_TABLE} "
            "WHERE embedding MATCH ? AND k = ? "
            "AND project_id = ? AND source_type = ? ORDER BY distance",
            (sqlite_vec.serialize_float32(qv), max(top_k * 2, top_k + 2),
             project_id, source_type),
        )
        want = {r[0]: float(r[1]) for r in cur.fetchall()}
        if not want:
            return []
        orms = (
            db.query(VectorChunkORM)
            .filter(VectorChunkORM.id.in_(list(want.keys())))
            .filter_by(project_id=project_id, source_type=source_type)
            .all()
        )
        hits = [
            SearchHit(o.id, o.source_type, o.source_id, o.chunk_text,
                      round(1.0 / (1.0 + want[o.id]), 6))
            for o in orms if o.id in want
        ]
        hits.sort(key=lambda h: -h.score)
        return hits[:top_k]

    def count(self, db: Session, project_id: str | None = None) -> int:
        return BruteVectorStore().count(db, project_id)


def remove_project_index(db: Session, project_id: str) -> int:
    """删除某项目的全部向量块（ORM 主表 + vec_index 虚拟表）。

    作品级联删除必须调它：`vector_chunks` 没有外键约束，项目删了向量不会自动走，
    会留下孤儿数据（2026-09-10 实测：删作品后残留 10 块）。
    """
    try:
        conn = db.connection()
        cur = conn.exec_driver_sql(
            "SELECT id FROM vector_chunks WHERE project_id = ?", (project_id,))
        ids = [r[0] for r in cur.fetchall()]
        for cid in ids:
            conn.exec_driver_sql(f"DELETE FROM {VEC_TABLE} WHERE chunk_id = ?", (cid,))
        conn.exec_driver_sql("DELETE FROM vector_chunks WHERE project_id = ?", (project_id,))
        return len(ids)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[vector_store] 清理项目向量失败: {type(e).__name__}: {str(e)[:80]}")
        return 0


def rebuild_vec_index(db: Session) -> int:
    """从 `vector_chunks`（source of truth）全量重建 vec_index。

    用途：vec_index 是纯加速索引、可随时丢弃重建——schema 升级（如加辅助列）
    或索引与实际数据不一致时调它自愈。返回重建块数。
    """
    try:
        import sqlite_vec
        conn = db.connection()
        cur = conn.exec_driver_sql(
            "SELECT id, embedding_json, project_id, source_type FROM vector_chunks")
        rows = cur.fetchall()
        n = 0
        for cid, emb_json, pid, stype in rows:
            try:
                v = json.loads(emb_json or "[]")
            except Exception as e:  # noqa: BLE001
                # 重建索引时跳过损坏行（其余行仍可正常重建），但要留痕（Phase 3.5）
                logger.warning(
                    f"[vector_store] 重建时跳过向量损坏的块 id={str(cid)[:8]}: {type(e).__name__}: {e}"
                )
                continue
            if len(v) != EMBED_DIM:
                continue
            conn.exec_driver_sql(
                f"DELETE FROM {VEC_TABLE} WHERE chunk_id = ?", (cid,))
            conn.exec_driver_sql(
                f"INSERT INTO {VEC_TABLE}(chunk_id, embedding, project_id, source_type) "
                "VALUES(?, ?, ?, ?)",
                (cid, sqlite_vec.serialize_float32(_l2_normalize(v)), pid, stype),
            )
            n += 1
        return n
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[vector_store] 重建 vec_index 失败: {type(e).__name__}: {str(e)[:80]}")
        return 0


def vec_index_available(db: Session) -> bool:
    """vec_index 虚拟表存在**且 schema 含 project_id 辅助列**（工厂判据）。

    旧 schema（无辅助列）会被判为不可用 → 工厂回退 BruteVectorStore（结果正确只是慢），
    同时 database._ensure_vec_index 会在启动时把旧表重建掉。
    """
    try:
        cur = db.connection().exec_driver_sql(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name=?", (VEC_TABLE,)
        )
        row = cur.fetchone()
        if row is None:
            return False
        return "project_id" in (row[1] or "")
    except Exception as e:  # noqa: BLE001
        # 查不到 sqlite_master 只说明"无法确认可用"（保守回退 Brute 实现），但要留痕：
        # 否则「为什么一直在用慢的 Brute 实现」将没有线索（Phase 3.5）
        logger.warning(f"[vector_store] vec_index 可用性探测失败，回退 Brute 实现: {type(e).__name__}: {e}")
        return False


def get_store(db: Session) -> VectorStore:
    """工厂：vec_index 虚拟表可用 → SqliteVecStore；否则 BruteVectorStore。"""
    return SqliteVecStore() if vec_index_available(db) else BruteVectorStore()
