"""全局配置（脚手架占位）。

生产环境建议改用 pydantic-settings 从环境变量读取。此处用常量保持零额外依赖。
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
# 数据库移出项目目录（存放于用户主目录），避免打包/上传项目时泄露明文 API Key 与作品数据
DEFAULT_DB_URL = f"sqlite:///{Path.home() / '.ai_novel' / 'data' / 'novel_agent.db'}"
DB_BACKEND = "sqlite"  # sqlite | mysql
API_V1_PREFIX = "/api/v1"

# 温度/约束（对应 API接口规范.md §9）
TEMPERATURE_PRESETS = {
    "chapter": 0.4,      # 剧情生成 0.3~0.5
    "direction": 0.7,    # 走向推演
    "memory": 0.2,       # 记忆压缩
    "parse": 0.3,        # 设定解析
    "foreshadow": 0.5,   # 伏笔推演
}

# 章节字数硬约束（需求 2）
CHAPTER_WORD_MIN = 3000
CHAPTER_WORD_MAX = 5000
