"""向量索引编排层（A1+A2 的业务入口）：切块 → 调 embedding → 经 VectorStore 落库。

所有对外函数都保证「失败不炸主流程」：key 缺失 / API 失败 / 开关关闭
一律静默跳过并返回 0——向量检索是增强能力，绝不能阻断写后摄取。
"""
import uuid

from sqlalchemy.orm import Session

from app.models.orm import ChapterMemoryORM, ReferenceDocORM
from app.services import app_config, embedding_client
from app.services.vector_store import VectorRow, get_store

# 切块参数：中文叙事 ~500 字/块，段落边界对齐
CHUNK_SIZE = 500
CHUNK_OVERLAP = 0
KEY_VECTOR_INDEX = "retrieval.vector_index"
KEY_SILICONFLOW_KEY = "retrieval.siliconflow_key"

ST_REF_DOC = "ref_doc"
ST_CHAPTER_MEMORY = "chapter_memory"


def enabled(db: Session) -> bool:
    """总开关：app_config 控制（默认开）。key 缺失时 embed 阶段还会再拦一次。"""
    try:
        return bool(app_config.get(db, KEY_VECTOR_INDEX, True))
    except Exception:  # noqa: BLE001
        return False


def _chunk_text(text: str) -> list[str]:
    """按段落聚合切块：尽量在 \n\n 边界断开，单块 ≤CHUNK_SIZE 字。"""
    t = (text or "").strip()
    if not t:
        return []
    if len(t) <= CHUNK_SIZE:
        return [t]
    paras = [p.strip() for p in t.split("\n\n") if p.strip()]
    if not paras:
        paras = [t[i:i + CHUNK_SIZE] for i in range(0, len(t), CHUNK_SIZE)]
    chunks, buf = [], ""
    for p in paras:
        if len(p) > CHUNK_SIZE:
            # 单段超长：硬切
            if buf:
                chunks.append(buf)
                buf = ""
            for i in range(0, len(p), CHUNK_SIZE):
                chunks.append(p[i:i + CHUNK_SIZE])
            continue
        if len(buf) + len(p) + 2 <= CHUNK_SIZE:
            buf = f"{buf}\n\n{p}" if buf else p
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks


def index_chunks(db: Session, project_id: str, source_type: str, source_id: str,
                 chunks: list[str]) -> int:
    """把切块向量化入库。返回入库块数；任何失败返回 0（静默降级）。"""
    if not enabled(db) or not chunks:
        return 0

    # 竞态防护（2026-09-10 实测 e2e）：写后摄取是**异步后台线程**，若作者在摄取完成前
    # 删除了作品，级联清理跑在索引写入之前 → 向量被写进一个已不存在的项目，成为孤儿
    # （且 vec_index 是全局表，这些块会永久挤占其他项目的 KNN 名额）。
    # 建索引前先确认项目仍在；`__global__` 是全局资料池的虚拟 project_id，无 projects 行，须豁免。
    try:
        from app.services.reference_crud import GLOBAL_PROJECT_ID
        from app.models.orm import ProjectORM
        if project_id != GLOBAL_PROJECT_ID:
            if db.query(ProjectORM).filter_by(id=project_id).first() is None:
                print(f"[vector_index] 项目 {str(project_id)[:8]} 已不存在，跳过向量写入")
                return 0
    except Exception:  # noqa: BLE001
        pass  # 校验本身失败不应阻断索引（宁可写也不要静默不索引）

    try:
        vecs = embedding_client.embed_texts(chunks, db=db)
    except Exception as e:  # noqa: BLE001
        print(f"[vector_index] embedding 不可用，跳过索引: {type(e).__name__}: {str(e)[:120]}")
        return 0
    model = embedding_client.embed_model_name()
    store = get_store(db)
    rows = [
        VectorRow(
            chunk_id=str(uuid.uuid4()),
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            chunk_idx=i,
            chunk_text=c,
            model=model,
            vector=v,
        )
        for i, (c, v) in enumerate(zip(chunks, vecs))
    ]
    try:
        store.upsert(db, rows)
        return len(rows)
    except Exception as e:  # noqa: BLE001
        print(f"[vector_index] 向量入库失败: {type(e).__name__}: {str(e)[:120]}")
        return 0


def remove_source(db: Session, project_id: str, source_type: str, source_id: str) -> int:
    """删除某来源的全部向量块。失败静默。"""
    try:
        return get_store(db).delete_by_source(db, project_id, source_type, source_id)
    except Exception:  # noqa: BLE001
        return 0


def index_reference_doc(db: Session, doc) -> int:
    """对一份参考文档重建向量索引（先删旧块再入新块）。"""
    try:
        remove_source(db, doc.project_id, ST_REF_DOC, doc.id)
        return index_chunks(db, doc.project_id, ST_REF_DOC, doc.id,
                            _chunk_text(doc.content_text or ""))
    except Exception:  # noqa: BLE001
        return 0


def remove_reference_doc(db: Session, doc) -> int:
    return remove_source(db, doc.project_id, ST_REF_DOC, doc.id)


def reindex_project_references(db: Session, project_id: str) -> dict:
    """重建某项目全部参考文档的向量索引（幂等：先删旧块再入新块）。

    用途：配置好硅基流动 key 后对**存量**文档一次性补建索引
    （生命周期钩子只覆盖增量：上传/导入/删除）。
    返回 {"docs": 尝试篇数, "chunks": 入库块数}；无 key 时 chunks=0 不报错。
    """
    stats = {"docs": 0, "chunks": 0}
    try:
        docs = db.query(ReferenceDocORM).filter_by(project_id=project_id).all()
    except Exception:  # noqa: BLE001
        return stats
    for doc in docs:
        stats["docs"] += 1
        stats["chunks"] += index_reference_doc(db, doc)
    db.commit()
    return stats


def sync_after_ingest(db: Session, project_id: str, memory_id: str,
                      article_id: str | None = None) -> dict:
    """写后摄取完成后的向量同步钩子（ingestion 尾部调用）。

    1) 本章章级记忆 → 向量化入库（summary + hook + plot_points 拼合）；
    2) 本篇的篇章摘要文档（source=auto）内容已更新 → 重建其索引。
    """
    stats = {"memory_chunks": 0, "digest_chunks": 0}
    if not enabled(db):
        return stats

    try:
        mem = db.query(ChapterMemoryORM).filter_by(id=memory_id).first()
        if mem is not None:
            parts = [mem.summary or ""]
            if mem.ending_hook:
                parts.append(f"结尾钩子：{mem.ending_hook}")
            if mem.plot_points:
                parts.append("关键事件：" + "；".join(mem.plot_points))
            remove_source(db, project_id, ST_CHAPTER_MEMORY, mem.id)
            stats["memory_chunks"] = index_chunks(
                db, project_id, ST_CHAPTER_MEMORY, mem.id, _chunk_text("\n\n".join(x for x in parts if x)))
    except Exception as e:  # noqa: BLE001
        print(f"[vector_index] 章级记忆索引失败: {type(e).__name__}: {str(e)[:120]}")

    if article_id:
        try:
            doc = (
                db.query(ReferenceDocORM)
                .filter_by(project_id=project_id, article_id=article_id, source="auto")
                .first()
            )
            if doc is not None and (doc.content_text or "").strip():
                stats["digest_chunks"] = index_reference_doc(db, doc)
        except Exception as e:  # noqa: BLE001
            print(f"[vector_index] 篇章摘要索引失败: {type(e).__name__}: {str(e)[:120]}")
    return stats


def search_similar(db: Session, project_id: str, source_type: str,
                   query_text: str, top_k: int = 5) -> list:
    """对外检索入口（A3 Hybrid 将调用）：查询文本向量化 → KNN。失败返回 []。"""
    if not enabled(db) or not query_text.strip():
        return []
    try:
        vecs = embedding_client.embed_texts([query_text], db=db)
        return get_store(db).search(db, project_id, source_type, vecs[0], top_k=top_k)
    except Exception as e:  # noqa: BLE001
        print(f"[vector_index] 向量检索失败: {type(e).__name__}: {str(e)[:120]}")
        return []
