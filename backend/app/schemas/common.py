"""通用分页与查询参数。"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any


class Pagination(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
    order_by: Optional[str] = None
    desc: bool = False


class Paginated(BaseModel):
    items: List[Any] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
