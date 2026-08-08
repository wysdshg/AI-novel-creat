"""模块4：多厂商统一 API 网关（需求 7）。全局配置，不含 project_id。

真实实现：
- 模型配置的增删改查落库 model_configs 表；
- 列表接口对 api_key 掩码，详情接口返回完整密钥供编辑；
- 支持「设为默认」（唯一默认生成模型）；
- /models/test 真实请求厂商接口验证连通性与延迟，可传 model_id 复用已保存配置。
"""
from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session

from app.schemas.model import ModelConfigCreate, ModelConfigUpdate, ModelTestRequest
from app.core.response import ok
from app.core.database import get_session
from app.services import model_crud
from app.models.orm import ModelConfigORM

router = APIRouter(tags=["模型网关"])


@router.get("/models")
def list_models(db: Session = Depends(get_session)):
    return ok(model_crud.list_models(db))


@router.post("/models")
def create_model(body: ModelConfigCreate, db: Session = Depends(get_session)):
    return ok(model_crud.create_model(db, body))


@router.get("/models/{model_id}")
def get_model(model_id: str, db: Session = Depends(get_session)):
    m = model_crud.get_model(db, model_id)
    if not m:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="模型不存在")
    return ok(m)


@router.put("/models/{model_id}")
def update_model(model_id: str, body: ModelConfigUpdate, db: Session = Depends(get_session)):
    m = model_crud.update_model(db, model_id, body)
    if not m:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="模型不存在")
    return ok(m)


@router.delete("/models/{model_id}")
def delete_model(model_id: str, db: Session = Depends(get_session)):
    if not model_crud.delete_model(db, model_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="模型不存在")
    return ok({"deleted": model_id})


@router.post("/models/{model_id}/set-default")
def set_default(model_id: str, db: Session = Depends(get_session)):
    if not model_crud.set_default(db, model_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="模型不存在")
    return ok({"default": model_id})


@router.post("/models/test")
def test_model(body: ModelTestRequest, db: Session = Depends(get_session)):
    # 若携带 model_id，复用已保存配置填充连接字段
    if body.model_id:
        o: ModelConfigORM = db.query(ModelConfigORM).filter_by(id=body.model_id).first()
        if o:
            body.vendor = o.vendor
            body.api_base = o.api_base
            body.api_key = o.api_key
            body.model_name = o.model_name
    return ok(model_crud.test_connection(body))
