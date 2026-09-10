<div align="center">

# AI 小说创作智能体

**本机单人使用的长篇小说写作辅助工具**

用 AI 接管"人做不到"的事 —— 跨几十章的一致性、伏笔追踪、上下文压缩、设定校验、写后自动沉淀；
把故事结构、文风审美与最终成稿留给作者本人。

`Python 3.12` · `FastAPI` · `SQLAlchemy 2.0` · `Vue 3` · `Element Plus` · `SQLite`

[快速开始](#-快速开始) · [功能特性](#-功能特性) · [项目文档](#-项目文档) · [路线图](#️-路线图)

</div>

---

## 这是什么

写长篇小说时，真正难的不是"写一段"，而是**写到第 50 章还记得前 49 章发生了什么**：
人物性格不能崩、埋下的伏笔要能收回来、新写的情节不能违反已定的世界观设定。

本项目围绕这条主线做成一个闭环：

```
作者构思 / 商讨剧情 → AI 生成章节（流式，可中断）
                    → 写后自动沉淀（章级记忆 / 篇章摘要 / 走向建议 / 伏笔动作）
                    → 下一章自动带上前情、设定、伏笔
                    → 随时查看「埋了哪些伏笔没收」「前面发生过什么」
```

**题材无关**：架空王朝、都市、玄幻、科幻都可以 —— 题材差异通过「设定库 + 参考文档 + SKILL」承载，不硬编码进代码。
（仓库内的测试题材是宋式架空王朝探案/官场向，仅为示例。）

> 定位说明：这是**个人本机工具**，不产品化、不上云、不做多用户，所有设计都以"作者本人写得更快、更稳、不崩"为唯一判据。

## ✨ 功能特性

### 🖋️ 章节生成
- **流式生成**：SSE 实时输出、可随时中断；占位文案绝不污染正文
- **安全网三件套**：复读检测（小模型长文防鬼打墙）、去 AI 味扫描、内联设定校验
- **剧情商讨**：与 AI 反复推演剧情，可先加载资料与设定再作答

### 🧠 记忆与一致性
- **写后自动沉淀**：每章生成后自动抽取章级记忆、篇章摘要、走向建议、伏笔动作
- **伏笔全生命周期**：埋设 → 提示 → 回收（或标记烂尾），自动回注到后续章节的上下文
- **四级结构**：小说 → 卷 → 篇 → 章，级联管理
- **全局设定库 / 资料池 / 自定义 SKILL**：跨作品共享的世界观与写作规范

### 🔍 检索增强（RAG）
- **Hybrid 混合检索**：关键词 + 向量（bge-m3）双通道 RRF 融合，再经 bge-reranker-v2-m3 重排
- **实体图一跳扩展（GraphRAG）**：本章提到某角色，自动带出关系网、所属势力、关联地点
- **按需加载**：参考资料与设定走「目录 + 两阶段拉取」协议，不撑爆上下文窗口
- **优雅降级**：未配置检索 Key 时自动退回纯关键词检索，生成链路不受影响

### 📊 质量评估与观测
- **生成评估**：每次生成自动留档版本（配置快照 + 正文 + 指标），人工 1~5 分打分、同章多版本对比
- **用量计量**：按模型 / 场景 / 日期统计 token 消耗，如实区分厂商真实回流与估算
- **反馈回流**：作者改动正文时自动记录改动幅度与样本 —— 那正是 AI 反复做不好的地方
- **日志落盘**：`backend.log` 全量 + `error.log` 分级，含启动/退出标记与心跳取证（进程被杀 vs 优雅退出一眼可辨）

## 🏗️ 技术栈与架构

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 · Element Plus · Pinia · Vite |
| 后端 | Python 3.12 · FastAPI · SQLAlchemy 2.0 |
| 数据库 | SQLite 单文件（存于仓库外，`init_db` 自动建表，27 张表） |
| 模型接入 | OpenAI 兼容协议（ModelScope / GLM / SiliconFlow / DeepSeek…）· Claude · Ollama 本地 |
| 检索 | bge-m3 Embedding · sqlite-vec · RRF 融合 · bge-reranker-v2-m3 重排 |

```
├── backend/
│   ├── app/
│   │   ├── routers/          # 89 个 API 路径（149 个路由条目），统一 /api/v1 前缀
│   │   ├── services/         # 业务层：CRUD / 写后摄取 / 检索 / 评估 / 用量 / 反馈
│   │   ├── core/
│   │   │   ├── gateway/      # 模型适配器（OpenAI 兼容 / Claude / Ollama），加厂商零改引擎
│   │   │   ├── context/      # 上下文引擎：分层装配 + 预算裁剪
│   │   │   └── workflow_engine/  # 可视化工作流（DAG，8 种节点）
│   │   └── models/           # SQLAlchemy ORM（27 张表）
│   ├── tests/                # unit（208 用例）+ e2e（真机链路验收）
│   └── dev.py
├── frontend/src/
│   ├── views/                # 20 个页面（写作台 / 章节列表 / 评估 / 观测 / 设定库…）
│   ├── components/           # 商讨面板 / 生成对话框 / 走向卡片…
│   ├── store/                # Pinia（结构与当前作品状态）
│   └── api/                  # 后端接口封装
├── docs/                     # 7 份权威文档（见下方导航）
└── CHANGELOG.md              # 每次改动一行，可追溯
```

## 🚀 快速开始

### 环境要求

- Python **3.12**
- Node.js **22**
- 一个可用的模型服务（云端 OpenAI 兼容 API，或本地 [Ollama](https://ollama.com)）—— 检索增强为可选增强，不配置也能用

### 1. 克隆与安装

```bash
git clone https://github.com/wysdshg/AI-novel-creat.git
cd AI-novel-creat

# 后端依赖（建议 Python 3.12 虚拟环境）
python -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt

# 前端依赖
cd frontend && npm install && cd ..
```

### 2. 启动

开两个终端分别启动：

```bash
# 终端 1 —— 后端（端口 8000）
cd backend
..\.venv\Scripts\python.exe dev.py

# 终端 2 —— 前端（端口 5173）
cd frontend
npm run dev
```

- 写作台：<http://localhost:5173>
- API 文档（Swagger）：<http://127.0.0.1:8000/docs>
- 首次启动自动建表；仓库根的 `start_project.ps1` 是一键脚本备选

### 3. 配置模型

打开写作台 → **模型配置**，填入厂商 / API 地址 / Key / 模型名即可。
支持任何 OpenAI 兼容服务（ModelScope、GLM、SiliconFlow、DeepSeek…）、Claude 与本地 Ollama。

> 数据库位于**仓库之外**（`C:\Users\<用户>\.ai_novel\data\novel_agent.db`），所有作品数据与密钥都只存本机。

## 🔑 密钥说明（⚠️ 切勿提交到仓库）

| 用途 | 存放位置 |
|---|---|
| 对话 / 章节生成模型 | `model_configs` 表（界面「模型配置」维护） |
| 向量检索（硅基流动，可选） | 环境变量 `NA_SILICONFLOW_KEY`，或界面写入 `app_configs.retrieval.siliconflow_key` |

## 🧪 测试

```bash
cd backend

# 单元测试（秒级）
..\.venv\Scripts\python.exe -m pytest tests/unit/

# 端到端（分钟级，需要真实模型服务）
..\.venv\Scripts\python.exe tests/e2e/test_full_chain.py        # 生成质量基线
..\.venv\Scripts\python.exe tests/e2e/test_retrieval_chain.py   # 检索注入验收
..\.venv\Scripts\python.exe tests/e2e/test_on_demand_load.py    # 按需加载协议
```

## 📚 项目文档

| 文件 | 内容 |
|---|---|
| [`docs/01-项目目标.md`](docs/01-项目目标.md) | 目标 · 边界 · 成功标准 · 不做清单 |
| [`docs/02-已实现清单.md`](docs/02-已实现清单.md) | **实测版**功能状态（每条带验证方式与日期） |
| [`docs/03-规划与进行中.md`](docs/03-规划与进行中.md) | 路线图 · 模块去留决策 |
| [`docs/04-踩坑档案.md`](docs/04-踩坑档案.md) | 踩坑记录（模型行为 / 环境 / 代码） |
| [`docs/05-架构与接口.md`](docs/05-架构与接口.md) | 架构 · 路由 · SSE 事件 · 数据模型 · 环境变量 |
| [`docs/06-AI工作手册.md`](docs/06-AI工作手册.md) | AI 协作工作手册（铁律与索引） |
| [`docs/07-任务分发手册.md`](docs/07-任务分发手册.md) | 多 agent 任务投递单规范 |

## 🗺️ 路线图

| 阶段 | 内容 | 状态 |
|---|---|---|
| Phase 0 | 工程立规：pytest 骨架 / 日志落盘 / CHANGELOG | ✅ |
| Phase 1 | 止血：隐私清理 / 错误处理 / 假绿灯下架 | ✅ |
| Phase 2 | 主闭环：伏笔全生命周期 / 章节列表 / 级联删除 | ✅ |
| Phase 3 | 工程质量：死代码清理 / SSE 统一 / 全量异常补日志 | ✅ |
| Phase R | 检索升级：Hybrid 融合 + 重排 + 实体图扩展 | ✅ |
| Phase 4 | Agent 闭环：生成评估 / 用量观测 / 反馈回流 | 🟡 核心已落地 |
| Phase 5 | 体验完善：分页 / 回收站 / 导出 | ⬜ |
| Phase 6 | 工具调用（function calling）扩展 | 📋 规划中 |

详细进展见 [`docs/03-规划与进行中.md`](docs/03-规划与进行中.md)，逐条变更见 [`CHANGELOG.md`](CHANGELOG.md)。

## 🤖 AI 协作

本项目由 AI 深度参与开发（设计 / 实现 / 测试 / 文档 / 排障全链路）。
AI 助手接手任务请从 **[`AIREADME.md`](AIREADME.md)** 开始 —— 它是 AI 的任务入口，与面向人的 README 分离。

---

<div align="center">

个人项目 · 用技术给写作加点耐心

</div>
