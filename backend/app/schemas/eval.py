"""评估（Phase 4.1 最小 eval）：请求模型。"""
from typing import Optional

from pydantic import BaseModel, Field


class EvalScoreRequest(BaseModel):
    """给某个生成版本打分。

    分数语义：1=不能用，2=勉强，3=及格，4=好，5=可以直接用。
    """

    score: int = Field(..., ge=1, le=5, description="1~5 总分")
    comment: Optional[str] = Field(None, description="备注：哪里好、哪里退步")
    dimensions: Optional[dict] = Field(
        None, description="预留：多维度打分（文笔/一致性/设定符合度），当前不用"
    )
