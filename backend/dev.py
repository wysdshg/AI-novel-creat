"""开发期启动入口（根治「改后端必须手动重启」坑）。

直接 `python dev.py` 即可，已默认开启 uvicorn reload：
- 修改任意 backend 代码后，服务自动热重启，无需手动杀进程；
- 启动时会调用 init_db，自动建表并对已有表增量迁移（新增 ORM 列无需手敲 ALTER）。

生产/稳定调试如需关闭 reload，用环境变量 DEV_RELOAD=0 启动。
"""
import os

import uvicorn

if __name__ == "__main__":
    reload = os.environ.get("DEV_RELOAD", "1") != "0"
    uvicorn.run(
        "main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        reload=reload,
        reload_dirs=["app", "main.py"],
    )
