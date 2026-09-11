"""篇规划 API（Phase 7.2，路径前缀在 main.py 拼 /api/v1）。

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/projects/{pid}/articles/{aid}/plan/generate` | 生成本篇章计划（body: hint/n_chapters/force_free） |
| GET | `/projects/{pid}/articles/{aid}/plan` | 读当前计划（没有返回 null） |
| PUT | `/projects/{pid}/articles/{aid}/plan` | 保存行级编辑（表格直接改） |
| POST | `…/plan/refine-line` | **AI 只改一行**（其余行原样） |
| POST | `…/plan/confirm` | 作者拍板（draft → confirmed，此后生成注入本章任务） |

计划行字段：`{no, beat, summary, new_chars[], recall_chars[], target_words, hook, template_ref}`。
防幻觉：召回角色经后端校验（查无此人剔除）；新角色只进 `planned_chars`，拍板后走待确认实体。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.services import plan_crud

router = APIRouter(tags=["篇规划"])


class GenerateBody(BaseModel):
    hint: str = Field("", description="作者口述（最高优先级）")
    n_chapters: int = Field(8, ge=2, le=40, description="本篇章数")
    force_free: bool = Field(False, description="跳过模板检索，强制自由规划")


class RefineLineBody(BaseModel):
    line_no: int = Field(..., ge=1)
    instruction: str = Field(..., min_length=2, description="修改要求")


class SaveLinesBody(BaseModel):
    lines: list[dict]
    notes: str | None = None


@router.post("/projects/{project_id}/articles/{article_id}/plan/generate",
             summary="生成本篇章计划（模板 + 上下文 + 口述）")
def generate_plan(project_id: str, article_id: str, body: GenerateBody,
                  db: Session = Depends(get_session)):
    try:
        return ok(plan_crud.generate_plan(db, project_id, article_id, hint=body.hint,
                                          n_chapters=body.n_chapters,
                                          force_free=body.force_free))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/articles/{article_id}/plan", summary="读当前计划")
def get_plan(project_id: str, article_id: str, db: Session = Depends(get_session)):
    return ok(plan_crud.get_plan(db, project_id, article_id))     # None = 还没规划


@router.put("/projects/{project_id}/articles/{article_id}/plan", summary="保存行级编辑")
def save_plan(project_id: str, article_id: str, body: SaveLinesBody,
              db: Session = Depends(get_session)):
    try:
        return ok(plan_crud.save_lines(db, project_id, article_id,
                                       lines=body.lines, notes=body.notes))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/articles/{article_id}/plan/refine-line",
             summary="AI 只改一行（其余行原样）")
def refine_line(project_id: str, article_id: str, body: RefineLineBody,
                db: Session = Depends(get_session)):
    try:
        return ok(plan_crud.refine_line(db, project_id, article_id,
                                        line_no=body.line_no, instruction=body.instruction))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/articles/{article_id}/plan/confirm", summary="拍板确认")
def confirm_plan(project_id: str, article_id: str, db: Session = Depends(get_session)):
    try:
        return ok(plan_crud.confirm_plan(db, project_id, article_id))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
