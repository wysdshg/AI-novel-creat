# AI 小说创作智能体

本机单人使用的**长篇小说写作辅助工具**。

- 后端：FastAPI + SQLAlchemy 2.0 + SQLite
- 前端：Vue 3 + Element Plus + Pinia + Vite
- 定位：本机单人写作工具 —— 不产品化、不上云、不做多用户

## 功能概览

| 能力 | 说明 |
|---|---|
| 四级结构 | 小说 → 卷 → 篇 → 章（删卷级联删篇+章） |
| 章节流式生成 | SSE 实时输出；内联设定校验 + 去 AI 味扫描 + 复读检测安全网 |
| 写后摄取 | 自动抽取章级记忆 / 篇章摘要 / 走向建议 / 伏笔动作，供后续章节回注 |
| **检索增强** | 关键词 + 向量（bge-m3）双通道 **RRF 融合** → **rerank**（bge-reranker-v2-m3）重排 |
| **实体图一跳扩展** | 本章要点提及某角色时，自动带出关系网 / 所属势力 / 关联地点（GraphRAG） |
| **按需加载** | 参考文档与设定库走「目录 + `LOAD_REFS` / `LOAD_SETTING` 两阶段」协议，不撑爆上下文 |
| 资料库 | 角色 / 势力 / 地点 / 关系 / 技能 / 伏笔 / 全局设定库 / 全局参考资料池 |
| 剧情商讨 | 与 AI 反复推演剧情，可加载资料与设定后再作答 |

## 文档入口

**所有信息以 `docs/` 下这 7 份为准**，其他文档均已过时并归档到 `docs/_archive/`（不要读）。

| 文件 | 内容 |
|---|---|
| [`docs/06-AI工作手册.md`](docs/06-AI工作手册.md) | **开工必读**：索引 / 铁律 / 常见误判 |
| [`docs/01-项目目标.md`](docs/01-项目目标.md) | 目标 · 边界 · 成功标准 · 不做清单 |
| [`docs/02-已实现清单.md`](docs/02-已实现清单.md) | **实测版**功能状态（哪些真能用） |
| [`docs/03-规划与进行中.md`](docs/03-规划与进行中.md) | 路线图 · 模块去留决策 |
| [`docs/04-踩坑档案.md`](docs/04-踩坑档案.md) | 踩坑记录（改提示词 / 参数前必读） |
| [`docs/05-架构与接口.md`](docs/05-架构与接口.md) | 架构 · 路由 · SSE 事件 · 数据模型 |
| [`docs/07-任务分发手册.md`](docs/07-任务分发手册.md) | 多 agent 任务投递单规范 |

改动记录见 [`CHANGELOG.md`](CHANGELOG.md)。

## 启动

```powershell
cd E:\AI小说创作
powershell -ExecutionPolicy Bypass -File .\start_project.ps1
```

- 后端 `http://127.0.0.1:8000/docs` ｜ 前端 `http://localhost:5173`
- Python 必须用项目内虚拟环境：`.venv\Scripts\python.exe`
- 改完后端代码**必须手动重启**（共享盘 uvicorn reload 不生效），详见 `docs/04-A1`
- 前端构建校验：`npm run build -- --outDir dist-test`（默认清 `dist` 会被安全钩子拦截）

## 测试

```bash
cd backend

# 单元测试（秒级，改任何后端代码后必跑）
..\.venv\Scripts\python.exe -m pytest tests/unit/

# 端到端（分钟级，改生成 / 检索 / 按需加载后跑）
..\.venv\Scripts\python.exe tests/e2e/test_full_chain.py        # 生成质量基线
..\.venv\Scripts\python.exe tests/e2e/test_retrieval_chain.py   # 检索注入验收
..\.venv\Scripts\python.exe tests/e2e/test_on_demand_load.py    # 按需加载两阶段协议
```

测试规范见 [`backend/tests/README.md`](backend/tests/README.md)。e2e 脚本自带清理，创建的测试作品跑完即删。

## 配置密钥（⚠️ 切勿提交到仓库）

所有密钥只存**本机数据库**，不写进任何代码文件：

| 用途 | 存放位置 |
|---|---|
| 对话 / 章节生成模型 | `model_configs` 表（界面「模型配置」维护） |
| 向量检索（硅基流动 bge-m3 / reranker） | 环境变量 `NA_SILICONFLOW_KEY`，或界面写入 `app_configs.retrieval.siliconflow_key` |

数据库位于**仓库目录之外**：`C:\Users\<用户>\.ai_novel\data\novel_agent.db`。
`.gitignore` 已排除 `.workbuddy/`、`backend/data/`、`frontend/dist*/` 等；提交前建议自查：

```bash
git grep -n "sk-" -- .        # 应为空（已提交内容）
git status --short            # 确认没有 .env / *.db / 密钥文件
```

## 环境要求

- Python 3.12（项目自带 `.venv`）
- Node.js 22
- 向量检索为可选增强：未配置硅基流动 Key 时自动降级为纯关键词检索，生成链路不受影响
