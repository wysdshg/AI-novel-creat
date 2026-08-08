"""参考文档 CRUD 服务（分作品隔离，project_id 过滤）。

提供 get_references_corpus() 供后续「章节生成」模块检索拼接，
将本作品全部参考文档文本拼为一段上下文，直接注入生成 Prompt。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.orm import ReferenceDocORM
from app.schemas.reference import ReferenceDocCreate, ReferenceDoc, ReferenceDocSummary

# 单次正文上限（字符），防止超大文档撑爆上下文；超过仅截断并标注。
MAX_CONTENT_CHARS = 200_000


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_summary(o: ReferenceDocORM) -> ReferenceDocSummary:
    return ReferenceDocSummary.model_validate(o)


def _to_full(o: ReferenceDocORM) -> ReferenceDoc:
    return ReferenceDoc.model_validate(o)


def list_references(db: Session, project_id: str) -> list[ReferenceDocSummary]:
    rows = (
        db.query(ReferenceDocORM)
        .filter_by(project_id=project_id)
        .order_by(ReferenceDocORM.created_at)
        .all()
    )
    return [_to_summary(r) for r in rows]


def create_reference(db: Session, project_id: str, data: ReferenceDocCreate) -> ReferenceDoc:
    content = data.content_text or ""
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + "\n…(内容超出上限，已截断)"
    now = _now()
    o = ReferenceDocORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        filename=data.filename,
        content_type=data.content_type or "text/plain",
        size=data.size or len(content.encode("utf-8")),
        content_text=content,
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_full(o)


def get_reference(db: Session, project_id: str, doc_id: str) -> ReferenceDoc | None:
    o = db.query(ReferenceDocORM).filter_by(project_id=project_id, id=doc_id).first()
    return _to_full(o) if o else None


def delete_reference(db: Session, project_id: str, doc_id: str) -> bool:
    o = db.query(ReferenceDocORM).filter_by(project_id=project_id, id=doc_id).first()
    if o is None:
        return False
    db.delete(o)
    db.commit()
    return True


def get_references_corpus(db: Session, project_id: str, limit: int = 10) -> str:
    """检索本作品参考文档，拼为一段上下文文本，供 AI 生成时读取。

    limit: 最多拼接的文档数（按上传顺序）。返回空串表示无参考文档。
    """
    rows = (
        db.query(ReferenceDocORM)
        .filter_by(project_id=project_id)
        .order_by(ReferenceDocORM.created_at)
        .limit(limit)
        .all()
    )
    if not rows:
        return ""
    blocks = []
    for i, o in enumerate(rows, 1):
        blocks.append(
            f"【参考文档 {i}：{o.filename}】\n{o.content_text}\n"
        )
    return "\n\n".join(blocks)
