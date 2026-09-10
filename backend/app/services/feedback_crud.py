"""反馈回流（Phase 4.3，2026-09-10）。

记录「作者对 AI 产出做了什么」—— 这是**最强的改进信号**，此前完全被丢弃，
导致模型下次照犯同样的错。

当前覆盖 `chapter_edit`：作者改动 AI 生成的正文时，对比**该章最新的 AI 版本**
（`chapter_variants`）与改动后的正文，记下改动幅度与摘要。

设计取舍：
- 只存**统计特征 + 少量样本**，不存改后全文 —— 全文已在 `chapters.content` 里，
  重复存既翻倍占用、又容易与正文不一致。
- 用 `difflib` 算相似度判断"是否真的改了"：只是点了保存（相似度≈1）不记，避免噪音淹没信号。

**为什么这有用**：作者改动的地方，恰恰是 AI 反复做不好的地方（比如总爱加总结句、
总把对话写得太书面）。攒够样本后可以回头看"我最常删掉什么"，据此改提示词 ——
这就是「反馈闭环」从 ❌ 变成 ✅ 的第一步。
"""
import difflib
import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.orm import ChapterVariantORM, FeedbackRecordORM

logger = logging.getLogger(__name__)

# 相似度 >= 该阈值视为"没实质改动"（仅空白/标点差异），不记反馈
NO_CHANGE_RATIO = 0.999
SAMPLE_CHARS = 200


def record_chapter_edit(db: Session, project_id: str, chapter_id: str,
                        before: str, after: str) -> dict | None:
    """对比并记录一次正文改动。**失败静默**。

    返回记下的 detail（无实质改动 / 异常时返回 None）。
    """
    try:
        before = before or ""
        after = after or ""
        if before == after:
            return None
        ratio = difflib.SequenceMatcher(None, before, after).ratio()
        if ratio >= NO_CHANGE_RATIO:
            return None  # 只是保存了一下，不算反馈

        # 对照的 AI 版本：该章最新的一条留档（Phase 4.1 机制）
        v = (
            db.query(ChapterVariantORM)
            .filter_by(chapter_id=chapter_id)
            .order_by(ChapterVariantORM.created_at.desc())
            .first()
        )
        detail = {
            "before_len": len(before),
            "after_len": len(after),
            "delta_len": len(after) - len(before),
            "similarity": round(ratio, 4),
            "change_ratio": round(1 - ratio, 4),   # 改动幅度，越大说明作者动得越多
            "sample_before": before[:SAMPLE_CHARS],
            "sample_after": after[:SAMPLE_CHARS],
        }
        db.add(FeedbackRecordORM(
            id=uuid.uuid4().hex,
            project_id=project_id,
            kind="chapter_edit",
            target_id=chapter_id,
            variant_id=v.id if v else None,
            detail=detail,
            created_at=datetime.utcnow(),
        ))
        db.commit()
        logger.info(
            f"[feedback] 记录正文改动 chapter={str(chapter_id)[:8]} "
            f"相似度={ratio:.3f} 长度 {len(before)}→{len(after)}"
        )
        return detail
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[feedback] 记录改动失败（不影响保存）: {type(e).__name__}: {e}")
        try:
            db.rollback()
        except Exception as e2:  # noqa: BLE001
            logger.debug(f"[feedback] rollback 失败: {type(e2).__name__}: {e2}")
        return None


def _to_dict(r: FeedbackRecordORM) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "kind": r.kind,
        "target_id": r.target_id,
        "variant_id": r.variant_id,
        "detail": r.detail or {},
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def list_feedback(db: Session, *, project_id: str | None = None,
                  kind: str | None = None, limit: int = 100) -> list[dict]:
    """列出反馈记录（时间倒序）。"""
    q = db.query(FeedbackRecordORM)
    if project_id:
        q = q.filter(FeedbackRecordORM.project_id == project_id)
    if kind:
        q = q.filter(FeedbackRecordORM.kind == kind)
    rows = q.order_by(FeedbackRecordORM.created_at.desc()).limit(max(1, int(limit or 100))).all()
    return [_to_dict(r) for r in rows]


def stats(db: Session, *, project_id: str | None = None) -> dict:
    """聚合：改动次数、平均相似度、平均改动幅度。

    平均改动幅度是**最该盯的一个数** —— 它长期偏高说明 AI 出的稿子离你能用的标准差得远。
    """
    q = db.query(FeedbackRecordORM)
    if project_id:
        q = q.filter(FeedbackRecordORM.project_id == project_id)
    rows = q.all()
    if not rows:
        return {"total": 0, "avg_similarity": None, "avg_change_ratio": None, "by_kind": {}}
    sims = [r.detail.get("similarity", 1.0) for r in rows if isinstance(r.detail, dict)]
    by_kind: dict[str, int] = {}
    for r in rows:
        by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
    return {
        "total": len(rows),
        "avg_similarity": round(sum(sims) / len(sims), 4) if sims else None,
        "avg_change_ratio": round(1 - (sum(sims) / len(sims)), 4) if sims else None,
        "by_kind": by_kind,
    }


def clear(db: Session, *, project_id: str | None = None) -> int:
    """清空反馈记录（可选按项目）。"""
    try:
        q = db.query(FeedbackRecordORM)
        if project_id:
            q = q.filter(FeedbackRecordORM.project_id == project_id)
        n = q.delete(synchronize_session=False)
        db.commit()
        return int(n or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[feedback] 清空失败: {type(e).__name__}: {e}")
        try:
            db.rollback()
        except Exception as e2:  # noqa: BLE001
            logger.debug(f"[feedback] rollback 失败: {type(e2).__name__}: {e2}")
        return 0
