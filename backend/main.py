"""网页小说智能体 — FastAPI 入口（脚手架阶段）。

所有业务端点当前以「接口桩」形式存在：返回统一信封 + 占位/mock 数据，
或返回 50101（未实现）。后续功能开发按 API接口规范.md 落地，无需改动本文件结构。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.response import ok
from app.core.database import init_db
from app.routers import (
    projects,
    database,
    chapter,
    discussion,
    model,
    memory,
    foreshadow,
    direction,
    template,
    references,
)

app = FastAPI(
    title="网页小说智能体 API",
    description="B/S 小说创作专属智能体后端（脚手架阶段，仅接口契约）",
    version="0.1.0",
)

# 开发期放开 CORS，生产按域名收紧
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 统一挂载各模块路由；prefix 与 API接口规范.md 的 /api/v1 一致
for r in (projects, database, chapter, discussion, model, memory, foreshadow, direction, template, references):
    app.include_router(r.router, prefix="/api/v1")


# 启动时建表并写入示例作品，保证角色库等模块开箱可用
@app.on_event("startup")
def _startup():
    init_db()


@app.get("/api/v1/health", tags=["系统"])
def health_check():
    """健康检查，供前端/部署探针使用。"""
    return ok({"status": "up", "version": "0.1.0"})


@app.get("/", include_in_schema=False)
def root():
    return ok({"msg": "网页小说智能体 API（脚手架）。详见 /docs 与 API接口规范.md"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
