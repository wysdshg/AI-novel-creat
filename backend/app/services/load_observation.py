"""P0 观测层：记录每轮商讨对话「设定库/参考文件」实际加载情况。

动机（设定库加载机制演进的第一步）：
  当前设定库走「目录常驻 + 模型发 LOAD_SETTING 按需加载」，但没有任何数据记录
  「每轮模型到底请求了哪些设定、是否真的注入、是否短路（Pass1 直接作答）」。
  没有这批数据，后续的关联边（related_ids）、BM25 自动注入阈值、频率预载都只能拍脑袋。

本模块只做一件事：把观测数据落库 + 提供查询。任何异常只打印、不抛出——
观测绝不能阻断对话主流程（对用户零感知）。
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.orm import DiscussionLoadLogORM


logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.utcnow()


def record(
    db: Session,
    *,
    project_id: str,
    conversation_id: Optional[str] = None,
    chapter_id: Optional[str] = None,
    question: str = "",
    load_ref_ids: Optional[list] = None,
    load_setting_ids: Optional[list] = None,
    ref_loaded: bool = False,
    setting_loaded: bool = False,
    short_circuited: bool = False,
    pass1_failed: bool = False,
    model_id: Optional[str] = None,
    vendor: Optional[str] = None,
) -> None:
    """落一条观测记录。失败静默降级（打印日志），不影响调用方。"""
    try:
        o = DiscussionLoadLogORM(
            id=uuid.uuid4().hex,
            project_id=project_id,
            conversation_id=conversation_id,
            chapter_id=chapter_id,
            question=(question or "")[:2000],
            load_ref_ids=list(load_ref_ids or []),
            load_setting_ids=list(load_setting_ids or []),
            ref_loaded=bool(ref_loaded),
            setting_loaded=bool(setting_loaded),
            short_circuited=bool(short_circuited),
            pass1_failed=bool(pass1_failed),
            model_id=model_id,
            vendor=vendor,
            created_at=_now(),
        )
        db.add(o)
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[load_observation] 落库失败（忽略）: {e}")
        try:
            db.rollback()
        except Exception as e:  # noqa: BLE001
            # rollback 自身失败：连接已不可用。留痕（debug 级，避免与上面 warning 重复刷屏）Phase 3.5
            logger.debug(f"[load_observation] rollback 失败（连接可能已断开）: {type(e).__name__}: {e}")


def list_logs(
    db: Session,
    project_id: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """查询最近 N 条观测记录（默认全量最近 200 条；可按小说过滤）。"""
    q = db.query(DiscussionLoadLogORM)
    if project_id:
        q = q.filter(DiscussionLoadLogORM.project_id == project_id)
    rows = (
        q.order_by(DiscussionLoadLogORM.created_at.desc())
        .limit(max(1, min(limit, 1000)))
        .all()
    )
    return [
        {
            "id": r.id,
            "project_id": r.project_id,
            "conversation_id": r.conversation_id,
            "chapter_id": r.chapter_id,
            "question": (r.question or "")[:200],
            "load_ref_ids": r.load_ref_ids or [],
            "load_setting_ids": r.load_setting_ids or [],
            "ref_loaded": r.ref_loaded,
            "setting_loaded": r.setting_loaded,
            "short_circuited": r.short_circuited,
            "pass1_failed": r.pass1_failed,
            "model_id": r.model_id,
            "vendor": r.vendor,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
