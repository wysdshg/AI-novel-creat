"""评估 API（Phase 4.1 最小 eval，路径前缀在 main.py 拼 /api/v1）。

端点：
| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/projects/{pid}/chapters/{cid}/variants` | 列出该章全部生成版本（含最新评分） |
| GET | `/projects/{pid}/chapters/{cid}/variants/compare` | 对比视图（含均分与最高分配置） |
| GET | `/variants/{vid}` | 版本详情（含正文全文） |
| POST | `/variants/{vid}/eval` | 打分（1~5 总分 + 备注） |
| DELETE | `/variants/{vid}` | 删除版本（连同其评分） |

**设计要点**：版本**由生成链路自动留档**（见 `routers/chapter.py` 保存段），
本模块只管查询 / 打分 / 清理 —— 不要求用户手动"创建版本"，否则没人会用。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.schemas.eval import EvalScoreRequest
from app.services import eval_crud as svc

router = APIRouter(tags=["评估（最小 eval）"])


@router.get("/projects/{project_id}/chapters/{chapter_id}/variants", summary="列出章节的生成版本")
def list_variants(project_id: str, chapter_id: str, db: Session = Depends(get_session)):
    return ok(svc.list_variants(db, chapter_id))


@router.get(
    "/projects/{project_id}/chapters/{chapter_id}/variants/compare",
    summary="版本对比视图（均分 / 最高分及其配置）",
)
def compare_variants(project_id: str, chapter_id: str, db: Session = Depends(get_session)):
    return ok(svc.summarize(db, chapter_id))


@router.get("/variants/{variant_id}", summary="版本详情（含正文）")
def get_variant(variant_id: str, db: Session = Depends(get_session)):
    d = svc.get_variant(db, variant_id)
    if d is None:
        raise HTTPException(status_code=404, detail="版本不存在")
    return ok(d)


@router.post("/variants/{variant_id}/eval", summary="给版本打分（1~5 总分）")
def score_variant(variant_id: str, body: EvalScoreRequest, db: Session = Depends(get_session)):
    r = svc.score_variant(db, variant_id, body.score, body.comment, body.dimensions)
    if r is None:
        # 版本不存在 或 分数越界（Pydantic 已挡 1~5，这里是兜底）
        raise HTTPException(status_code=400, detail="打分失败：版本不存在，或分数超出 1~5")
    return ok(r)


@router.delete("/variants/{variant_id}", summary="删除版本")
def delete_variant(variant_id: str, db: Session = Depends(get_session)):
    if not svc.delete_variant(db, variant_id):
        raise HTTPException(status_code=404, detail="版本不存在")
    return ok({"deleted": variant_id})
