"""反馈回流 API（Phase 4.3，路径前缀在 main.py 拼 /api/v1）。

端点：
| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/feedback?project_id=&kind=&limit=` | 列出反馈记录（时间倒序） |
| GET | `/feedback/stats?project_id=` | 聚合：次数 / 平均相似度 / 平均改动幅度 |
| DELETE | `/feedback?project_id=` | 清空（可选按项目） |

**当前记录的是「作者改动 AI 正文」**（`kind=chapter_edit`），由 `PUT /chapters/{id}`
自动捕获（见 `routers/chapter.py`），不需要前端额外上报。

`avg_change_ratio` 是最该盯的数：长期偏高 = AI 出的稿子离"能直接用的标准"差得远。
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.services import feedback_crud as svc

router = APIRouter(prefix="/feedback", tags=["观测 · 反馈"])


@router.get("", summary="列出反馈记录")
def list_feedback(
    project_id: Optional[str] = Query(None, description="按项目过滤；不传=全局"),
    kind: Optional[str] = Query(None, description="chapter_edit / direction_rejected …"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_session),
):
    return ok(svc.list_feedback(db, project_id=project_id, kind=kind, limit=limit))


@router.get("/stats", summary="反馈聚合统计")
def feedback_stats(
    project_id: Optional[str] = Query(None, description="按项目过滤；不传=全局"),
    db: Session = Depends(get_session),
):
    return ok(svc.stats(db, project_id=project_id))


@router.delete("", summary="清空反馈记录")
def clear_feedback(
    project_id: Optional[str] = Query(None, description="只清该项目；不传=全部"),
    db: Session = Depends(get_session),
):
    return ok({"deleted": svc.clear(db, project_id=project_id)})
