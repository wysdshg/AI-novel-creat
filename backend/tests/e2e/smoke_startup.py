"""启动冒烟：模拟 FastAPI startup，验证路由装配 + 建表 + 预置 SKILL 安装。

运行（必须在 backend/ 下执行）：
  cd E:/AI小说创作/backend
  E:/AI小说创作/.venv/Scripts/python.exe tests/e2e/smoke_startup.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

# 1) 导入入口：若任一 router 装配出错会在此抛 ImportError
import main  # noqa: F401  (导入即验证所有路由 import 链)
from app.core.config import DEFAULT_DB_URL

routes = [
    (getattr(r, "methods", None), r.path)
    for r in main.app.routes
    if getattr(r, "path", "").startswith("/api/v1")
]
methods = sorted({m for ms, _ in routes for m in (ms or set())})
print(f"[smoke] 应用导入 OK，/api/v1 路由数={len(routes)}")
print(f"[smoke] HTTP 方法集={methods}")
print(f"[smoke] DB_URL={DEFAULT_DB_URL}")

# 2) 模拟 startup：建表 + 安装预置 SKILL
from app.core.database import init_db
from app.core import database as _db_mod
from app.services import seed_skills

init_db()
db = _db_mod.SessionLocal()
try:
    res = seed_skills.install(db)
    print(f"[smoke] 预置 SKILL 安装结果: created={len(res['created'])} "
          f"updated={len(res['updated'])} skipped={len(res['skipped'])} total={res['total']}")
finally:
    db.close()

# 3) 复核：从库里读回，确认表与数据都在
from app.models.orm import CustomSkillORM, ChapterMemoryORM, StageSummaryORM, AppConfigORM
db = _db_mod.SessionLocal()
try:
    skill_n = db.query(CustomSkillORM).count()
    mem_n = db.query(ChapterMemoryORM).count()
    stage_n = db.query(StageSummaryORM).count()
    cfg_n = db.query(AppConfigORM).count()
    print(f"[smoke] 库状态: skills={skill_n} chapter_memories={mem_n} "
          f"stage_summaries={stage_n} app_configs={cfg_n}")
finally:
    db.close()

print("[smoke] 启动冒烟通过 ✅")
sys.exit(0)
