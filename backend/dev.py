r"""开发期启动入口。

默认 **关闭** uvicorn reload（reload=False）：
- 在 `E:\` 共享盘 / 沙箱等环境下，reload 本就不生效（宿主监听不到代码改动，改完仍需手动重启）；
- 更重要：reload 会在 Windows 上用 subprocess 多拉一个「worker 孙进程」，
  在沙箱/容器里该孙进程会逃逸出沙箱跟踪的作业对象，变成**关不掉的孤儿端口进程**（见项目记忆 ⑤）。
  故默认关闭，从根上杜绝该问题。

如需在本机（非沙箱）手动开启热重启，设环境变量 `DEV_RELOAD=1` 启动。
启动时会调用 init_db，自动建表并对已有表增量迁移（新增 ORM 列无需手敲 ALTER）。
"""
import os

import uvicorn

if __name__ == "__main__":
    # 默认关闭 reload；仅当显式 DEV_RELOAD=1 时才开启（本机调试用，沙箱勿开）。
    reload = os.environ.get("DEV_RELOAD", "0") == "1"
    uvicorn.run(
        "main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        reload=reload,
        reload_dirs=["app", "main.py"],
    )
