"""pytest 全局配置。

DB 策略（B 方案完整版，2026-09-10）：
- `test_db` fixture 用 **monkeypatch 改 `app.core.database` 模块的
  DEFAULT_DB_URL + 重置惰性单例**（`_engine`/`SessionLocal`），指向 tmp 目录的
  独立 SQLite —— 生产零改动、真实数据零风险（get_engine() 引用的是
  database 模块自己的全局名，首次调用时才绑定，改模块属性即生效；
  probe_pipeline.py 已用同款手法验证过可行性）。
- 生产库 `C:\\Users\\w3013\\.ai_novel\\data\\novel_agent.db` 在单测进程里
  **永远不会被触碰**：testpaths 只含 tests/unit，e2e 是独立进程手动跑。

零依赖单测三类：
  1. 去重函数 _dedup_trailing_repeats（纯字符串处理）
  2. humanizer 打分（纯正则）
  3. 应用装配冒烟（import main + 路由计数；init_db 只挂在 startup 事件上，
     import 无副作用，不碰数据库）
"""
import sys
from pathlib import Path

# 双保险：pytest.ini 的 pythonpath=. 已覆盖常规路径，
# 这里兜底「直接指定文件路径跑」等 rootdir 漂移的场景。
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest


@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    """独立临时 SQLite 会话（B 方案 DB fixture）。

    - 每个测试一个全新库文件（tmp_path 每次唯一）；
    - monkeypatch 测试结束自动还原 database 模块原值；
    - init_db() 建表 + 自动迁移（不 seed SKILL，需要时测试内自己装）。
    """
    import app.core.database as dbmod

    db_file = tmp_path / "test.db"
    monkeypatch.setattr(dbmod, "DEFAULT_DB_URL", f"sqlite:///{db_file}")
    # 重置惰性单例：防同进程早前测试已把 engine 绑到别的库
    monkeypatch.setattr(dbmod, "_engine", None)
    monkeypatch.setattr(dbmod, "SessionLocal", None)
    dbmod.init_db()
    db = dbmod.SessionLocal()
    try:
        yield db
    finally:
        db.close()
