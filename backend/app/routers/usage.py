"""用量观测 API（Phase 4.2，路径前缀在 main.py 拼 /api/v1）。

端点：
| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/usage/summary?project_id=&days=` | 聚合统计：总量 / 按模型 / 按场景 / 按天趋势 / 最近明细 |
| DELETE | `/usage?project_id=` | 清空用量日志（可选按项目） |

说明：只统计 **token 数**，不算金额 —— 各厂商单价差异大且会变，需要时按 token 量自行换算。
`estimated=true` 表示该次调用厂商没回流 usage、由字符数估算（页面上会标注）。
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.services import usage_crud as svc

router = APIRouter(prefix="/usage", tags=["观测 · 用量"])


@router.get("/summary", summary="用量聚合统计")
def usage_summary(
    project_id: Optional[str] = Query(None, description="按项目过滤；不传=全局"),
    days: int = Query(30, ge=1, le=365, description="统计最近 N 天"),
    db: Session = Depends(get_session),
):
    return ok(svc.summary(db, project_id=project_id, days=days))


@router.delete("", summary="清空用量日志")
def clear_usage(
    project_id: Optional[str] = Query(None, description="只清该项目；不传=全部"),
    db: Session = Depends(get_session),
):
    return ok({"deleted": svc.clear(db, project_id=project_id)})
