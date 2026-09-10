"""模型配置服务（模块4：多厂商统一 API 网关的持久化层）。

- 列表对 api_key 做掩码，避免密钥明文外泄；详情接口返回完整密钥供编辑/测试。
- is_default 维护「唯一默认生成模型」：设置某个为默认时，其余自动取消。
- test_connection 经 gateway 适配器真实请求厂商接口，返回连通性与延迟。
"""
import time
import uuid

from sqlalchemy.orm import Session

from app.models.orm import ModelConfigORM
from app.schemas.model import (
    ModelConfig,
    ModelConfigCreate,
    ModelConfigUpdate,
    ModelTestRequest,
)
from app.core.gateway.registry import get_adapter
from app.core.response import ok


def _mask_key(key: str) -> str:
    if not key:
        return ""
    return f"***{key[-4:]}" if len(key) > 4 else "***"


def _to_schema(o: ModelConfigORM, mask: bool = True) -> ModelConfig:
    return ModelConfig(
        id=o.id,
        name=o.name,
        vendor=o.vendor,
        api_base=o.api_base,
        api_key=_mask_key(o.api_key) if mask else o.api_key,
        model_name=o.model_name,
        context_window=o.context_window,
        temperature=o.temperature,
        top_p=o.top_p,
        max_tokens=o.max_tokens,
        role=o.role,
        is_backup=o.is_backup,
        status=o.status,
        is_default=o.is_default,
        enable_thinking=o.enable_thinking,
    )


def list_models(db: Session) -> list[ModelConfig]:
    rows = db.query(ModelConfigORM).order_by(
        ModelConfigORM.is_default.desc(), ModelConfigORM.created_at
    ).all()
    return [_to_schema(r, mask=True) for r in rows]


def get_model(db: Session, model_id: str) -> ModelConfig | None:
    o = db.query(ModelConfigORM).filter_by(id=model_id).first()
    return _to_schema(o, mask=False) if o else None


def create_model(db: Session, data: ModelConfigCreate) -> ModelConfig:
    now = _now()
    make_default = data.is_default
    if make_default:
        db.query(ModelConfigORM).update({ModelConfigORM.is_default: False})
    o = ModelConfigORM(
        id=uuid.uuid4().hex,
        name=data.name,
        vendor=data.vendor,
        api_base=data.api_base,
        api_key=data.api_key,
        model_name=data.model_name,
        context_window=data.context_window,
        temperature=data.temperature,
        top_p=data.top_p,
        max_tokens=data.max_tokens,
        role=data.role,
        is_backup=data.is_backup,
        status=data.status,
        is_default=make_default,
        enable_thinking=data.enable_thinking,
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_schema(o, mask=True)


def update_model(db: Session, model_id: str, data: ModelConfigUpdate) -> ModelConfig | None:
    o = db.query(ModelConfigORM).filter_by(id=model_id).first()
    if not o:
        return None
    payload = data.model_dump(exclude_unset=True)
    if "api_key" in payload and payload["api_key"] == "":
        # 空字符串视为「不修改密钥」，保留原值
        payload.pop("api_key")
    for field, value in payload.items():
        setattr(o, field, value)
    o.updated_at = _now()
    if getattr(data, 'is_default', None) is True:
        db.query(ModelConfigORM).filter(ModelConfigORM.id != model_id).update(
            {ModelConfigORM.is_default: False}
        )
    db.commit()
    db.refresh(o)
    return _to_schema(o, mask=True)


def delete_model(db: Session, model_id: str) -> bool:
    o = db.query(ModelConfigORM).filter_by(id=model_id).first()
    if not o:
        return False
    db.delete(o)
    db.commit()
    return True


def set_default(db: Session, model_id: str) -> bool:
    o = db.query(ModelConfigORM).filter_by(id=model_id).first()
    if not o:
        return False
    db.query(ModelConfigORM).update({ModelConfigORM.is_default: False})
    o.is_default = True
    o.updated_at = _now()
    db.commit()
    return True


def get_default(db: Session) -> ModelConfigORM | None:
    o = db.query(ModelConfigORM).filter_by(is_default=True).first()
    if o:
        return o
    # 退化：取第一个 active 的 primary 模型
    return (
        db.query(ModelConfigORM)
        .filter_by(role="primary", status="active")
        .order_by(ModelConfigORM.created_at)
        .first()
    )


def resolve_model(db: Session, model_id: str | None = None) -> ModelConfigORM | None:
    """**取本轮要用的模型**：优先前端显式指定的 `model_id`，否则回退默认模型。

    返回 ModelConfigORM | None（None 表示无可用模型，调用方自行决定报错还是兜底）。

    ⚠️ 抽本函数前，这段「指定优先、否则默认」的逻辑在 `discussion.py` / `assist.py` /
    `chapter.py` 里**各写了一份**，且细节已经**漂移出真 bug**：

    - `chapter.py` 直接用 `db.query(ModelConfigORM).filter_by(id=...)` 取指定模型，
      **绕过了 active 状态校验**——前端若提交一个已停用（或已被删但缓存）的 model_id，
      就会拿它去真实调用并失败（其余两处都会回退默认）。
    - 三处对「什么算可用」的判定也不一致（有的只查 `status`，有的不查）。

    统一走本函数后：`model_id` 存在**且 `status == active`** 才采用，否则一律回退默认，
    语义只有一处、不再各自漂移。

    改造前 `chapter.py` 的 `use_model = default is not None and (default.status or "active") == "active"`、
    `assist.py` 的 `if default is None or (default.status or "active") != "active"` 这类
    调用方二次校验**不需要再写**——本函数已保证返回的一定是 active（或 None）。
    """
    if model_id:
        m = get_model(db, model_id)
        if m and (m.status or "active") == "active":
            return m
    d = get_default(db)
    # 默认模型也需过一遍 active 校验（历史数据可能停在 disabled）
    if d and (d.status or "active") != "active":
        return None
    return d


def test_connection(req: ModelTestRequest) -> dict:
    """真实连通性测试。调用前由路由层把 model_id 解析为各连接字段填入 req。"""
    config = {
        "api_base": req.api_base,
        "api_key": req.api_key,
        "model_name": req.model_name,
        "temperature": 0.4,
        "top_p": 0.9,
        "max_tokens": 6000,
    }
    try:
        adapter = get_adapter(req.vendor, config)
    except ValueError as e:
        return {"ok": False, "latency_ms": 0, "msg": str(e)}
    start = time.time()
    try:
        ok_conn = adapter.test_connection()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "latency_ms": int((time.time() - start) * 1000), "msg": str(e)[:200]}
    latency = int((time.time() - start) * 1000)
    return {
        "ok": bool(ok_conn),
        "latency_ms": latency,
        "msg": "连接成功" if ok_conn else "连接失败（厂商返回非 200）",
    }


def _now():
    from datetime import datetime
    return datetime.utcnow()
