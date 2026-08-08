# 后端 FastAPI 脚手架（接口桩）

网页小说智能体后端。**当前为脚手架阶段**：所有端点返回占位/mock，业务逻辑未实现，仅定义接口契约。

## 运行
```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
- OpenAPI 文档： http://localhost:8000/docs
- 健康检查： GET /api/v1/health

## 结构
- `core/`：config（温度/字数约束）、response（统一信封）、database（ORM 基类）、gateway（模型适配器基类 + 厂商注册表，多厂商热插拔扩展点）
- `schemas/`：Pydantic 请求/响应模型（11 类实体，对齐 API接口规范.md）
- `models/orm.py`：SQLAlchemy ORM 桩（11 张表，含分作品隔离注释）
- `services/stubs.py`：业务桩层（返回 mock，标注 TODO；真实实现后 routers 调用方式不变）
- `routers/`：9 个模块路由桩（projects / database / chapter / discussion / model / memory / foreshadow / direction / template）

## 约定
- 统一响应：`{"code":0,"message":"success","data":...,"trace_id":...}`
- 业务路径含 `{project_id}` 实现数据隔离（§1）
- 错误码见根目录 `API接口规范.md §0.7`

## 扩展
- 新增模块：routers/ 新建 → main.py 注册；services/ 补实现。
- 新增模型厂商：继承 `core/gateway/base.py:BaseModelAdapter` 并在 `registry.py` 注册。
