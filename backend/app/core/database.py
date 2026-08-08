"""数据库基础（真实 SQLite 连接）。

- 声明基类 Base 供所有 ORM 实体继承（models/orm.py 从此导入）；
- get_engine 惰性创建引擎；SessionLocal 提供会话工厂；
- init_db 在应用启动时建表，并写入与前端默认小说对齐的示例作品，
  保证角色库等模块开箱即可访问；
- get_session 是 FastAPI 依赖，提供请求级数据库会话。
"""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import DEFAULT_DB_URL

Base = declarative_base()

_engine = None
SessionLocal = None


def get_engine():
    global _engine, SessionLocal
    if _engine is None:
        # SQLite 不会自动创建上层目录，需提前建好 data/，否则报 unable to open database file
        if DEFAULT_DB_URL.startswith("sqlite"):
            db_path = Path(DEFAULT_DB_URL.replace("sqlite:///", "", 1))
            db_path.parent.mkdir(parents=True, exist_ok=True)
        # SQLite 在多线程（FastAPI）下需要关闭同线程检查
        connect_args = (
            {"check_same_thread": False}
            if DEFAULT_DB_URL.startswith("sqlite")
            else {}
        )
        _engine = create_engine(DEFAULT_DB_URL, future=True, connect_args=connect_args)
        SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def get_session():
    """FastAPI 依赖：请求级会话，自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _auto_migrate(engine):
    """SQLite 增量迁移：比对 ORM 定义与已有表结构，缺列则自动 ALTER TABLE ADD COLUMN。

    根治「新增 ORM 列后报 no such column」——SQLite 不支持 create_all 的增量变更，
    这里手动补齐缺失列，避免每次都要手工写 ALTER 或删库重建。
    仅处理「新增列」场景（脚手架阶段够用）；删除/重命名列不在范围内。
    """
    from sqlalchemy import inspect, text
    from sqlalchemy import String, Integer, Float, Boolean, DateTime, Text, JSON

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # 确保 ORM 已注册
    import app.models.orm  # noqa: F401

    added = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # 全新表交给下面的 create_all 处理
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing_cols:
                continue
            # 推导列类型（SQLAlchemy 方言无关名）
            py_type = col.type
            type_name = py_type.__class__.__name__.upper()
            # 统一映射为 SQLite 友好的类型名
            sqlite_type = {
                "STRING": "TEXT",
                "TEXT": "TEXT",
                "INTEGER": "INTEGER",
                "FLOAT": "REAL",
                "BOOLEAN": "INTEGER",
                "DATETIME": "TEXT",
                "JSON": "TEXT",
            }.get(type_name, "TEXT")
            nullable = "" if col.nullable else " NOT NULL"
            default = ""
            # 仅标量默认可用；函数型默认(如 datetime.utcnow) 用 Python 触发，无法内联到 DDL
            if col.default is not None and not callable(col.default.arg):
                dv = col.default.arg
                if isinstance(dv, bool):
                    default = f" DEFAULT {1 if dv else 0}"
                elif isinstance(dv, (int, float)):
                    default = f" DEFAULT {dv}"
                elif isinstance(dv, (str, list, dict)):
                    import json as _json
                    lit = _json.dumps(dv) if isinstance(dv, (list, dict)) else dv
                    default = f" DEFAULT '{lit}'"
            # 已有数据表上给非空列加默认值缺失会失败，稳妥起见：非空列又无默认值时放宽成可空
            if not col.nullable and not default:
                nullable = ""
            stmt = text(
                f'ALTER TABLE {table.name} ADD COLUMN {col.name} {sqlite_type}{nullable}{default}'
            )
            with engine.begin() as conn:
                conn.execute(stmt)
            added.append(f"{table.name}.{col.name} ({sqlite_type})")
    return added


def init_db():
    """建表 + 增量迁移。幂等，可重复调用。

    1) create_all 负责新建尚未存在的表；
    2) _auto_migrate 负责给已有表补齐 ORM 中新增的列（SQLite 不支持自动增量变更）。
    """
    engine = get_engine()
    import app.models.orm  # noqa: F401
    Base.metadata.create_all(bind=engine)
    try:
        added = _auto_migrate(engine)
        if added:
            print(f"[init_db] 自动迁移新增列: {', '.join(added)}")
    except Exception as e:  # 迁移失败不应阻断启动
        print(f"[init_db] 自动迁移跳过/失败: {e}")
