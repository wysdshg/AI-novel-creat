"""`model_crud.resolve_model` 单一实现（Phase 3.4）。

背景：抽本函数前，「取本轮要用的模型」在 **4 处**各写了一份，且语义已漂移出真 bug：

- `discussion.py::_resolve_model`：指定 model_id 且 status==active 才用，否则回退默认（正确）；
- `assist.py`：同上，但多写了一道 `default.status != active → fail` 的二次校验（重复）；
- `chapter.py`：`db.query(ModelConfigORM).filter_by(id=body.model_id).first()`——
  **直接按 id 取、完全绕过 active 校验**（真 bug：已停用的模型会被拿去真实调用）；
- `config_command.py`：同 assist 又一份。

现在统一为 `model_crud.resolve_model`，本文件锁死其语义，防止再次漂移。
"""
import uuid

import pytest

from app.models.orm import ModelConfigORM
from app.services import model_crud


def _mk(db, *, name, status="active", is_default=False, role="primary"):
    o = ModelConfigORM(
        id=uuid.uuid4().hex,
        name=name,
        vendor="custom",          # 须是 ModelConfig schema 的 Literal 之一
        api_base="https://example.invalid/v1",
        api_key="sk-test",
        model_name="test-model",
        role=role,                # 须是 primary | memory | parse | foreshadow
        status=status,
        is_default=is_default,
    )
    db.add(o)
    db.commit()
    return o


# ---------- 指定 model_id 优先 ----------

def test_explicit_active_model_wins(test_db):
    db = test_db
    default = _mk(db, name="默认模型", is_default=True)
    other = _mk(db, name="另一个模型")

    got = model_crud.resolve_model(db, other.id)
    assert got is not None and got.id == other.id
    assert got.id != default.id


def test_explicit_inactive_model_falls_back_to_default(test_db):
    """核心回归：指定一个 **已停用** 的 model_id 时必须回退默认，而不是直接用它。

    这正是 `chapter.py` 原实现在做的事（`filter_by(id=...)` 不看 status）——
    前端提交停用模型 id 时会真实调用并失败。
    """
    db = test_db
    default = _mk(db, name="默认模型", is_default=True)
    disabled = _mk(db, name="已停用模型", status="disabled")

    got = model_crud.resolve_model(db, disabled.id)
    assert got is not None
    assert got.id == default.id, "停用模型不得被采用，必须回退默认"
    assert got.status == "active"


def test_explicit_unknown_id_falls_back_to_default(test_db):
    db = test_db
    default = _mk(db, name="默认模型", is_default=True)
    got = model_crud.resolve_model(db, "no_such_id_" + uuid.uuid4().hex)
    assert got is not None and got.id == default.id


# ---------- 不传 model_id ----------

def test_no_model_id_returns_default(test_db):
    db = test_db
    default = _mk(db, name="默认模型", is_default=True)
    _mk(db, name="干扰模型")
    got = model_crud.resolve_model(db)
    assert got is not None and got.id == default.id


def test_no_model_id_no_default_falls_back_to_first_active_primary(test_db):
    """无 is_default 时 `get_default` 退化取第一个 active primary 模型。"""
    db = test_db
    first = _mk(db, name="第一个 active primary")
    _mk(db, name="第二个 active primary")
    got = model_crud.resolve_model(db)
    assert got is not None and got.id == first.id


def test_inactive_default_returns_none(test_db):
    """历史脏数据：某模型标了 is_default 但 status 不是 active → 视为无可用模型。

    调用方（assist / chapter / config_command）据 None 给出「请先配置默认模型」提示。
    """
    db = test_db
    _mk(db, name="默认但已停用", is_default=True, status="disabled")
    assert model_crud.resolve_model(db) is None


def test_empty_db_returns_none(test_db):
    assert model_crud.resolve_model(test_db) is None


def test_explicit_model_wins_even_when_no_default_exists(test_db):
    db = test_db
    only = _mk(db, name="唯一模型", status="active", is_default=False, role="parse")
    got = model_crud.resolve_model(db, only.id)
    assert got is not None and got.id == only.id


# ---------- 单一实现：调用方不得再自写 ----------

@pytest.mark.parametrize("modpath", [
    "app.routers.chapter",
    "app.routers.assist",
    "app.routers.discussion",
    "app.services.config_command",
])
def test_callers_no_longer_hand_roll_model_resolution(modpath):
    """上述模块不得再出现「按 id 直接查 / 二次 status 校验」的手写逻辑。

    允许的是调用 `model_crud.resolve_model` 或它的薄别名 `_resolve_model`。

    ⚠️ 断言前必须**剥掉注释与 docstring**：本次重构恰好在这些文件里留了
    「原先这里是 filter_by(id=...)」这类说明性注释，直接扫全文会误报。
    故用 AST 取真实代码（去掉 docstring），再逐行剔除 `#` 注释。
    """
    import ast
    import importlib
    import inspect
    import re

    mod = importlib.import_module(modpath)
    tree = ast.parse(inspect.getsource(mod))

    # 去掉所有 docstring 节点（模块/类/函数级）
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:]

    code_lines = []
    for line in ast.unparse(tree).splitlines():
        stripped = line.split("#", 1)[0]
        if stripped.strip():
            code_lines.append(stripped)
    code = "\n".join(code_lines)

    # 不该再有 filter_by(id=body.model_id)（chapter.py 的原 bug 写法）
    assert not re.search(r"filter_by\(\s*id\s*=\s*body\.model_id", code), \
        f"{modpath} 又出现了绕过 active 校验的按 id 直查"

    # 不该再有「取 default 后再手工判 status」的二次校验
    assert not re.search(r"(default|m|d)\.status\s*or\s*[\"']active[\"']", code), \
        f"{modpath} 又出现了手写的 active 判定（应由 resolve_model 统一保证）"
