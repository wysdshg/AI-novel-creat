# 网页小说创作智能体 — 项目接力说明（README）

> 面向**下一任开发者 / Agent** 的上手与交接文档。读完本文件可在 5 分钟内接手。
> 配套文档：`API接口规范.md`（接口契约）、`PROJECT_REQUIREMENTS.md`（11 项需求落点）、`docs/架构设计-上下文与记忆引擎.md`（上下文引擎/记忆层/去AI味/SKILL调度/接线五大模块）、`.workbuddy/memory/2026-08-08.md`（本会话详细改动史）。
> 最后更新：2026-08-08

---

## 1. 这是什么

一个 B/S 架构的小说创作专属智能体。当前已搭好**前端界面 + 后端 REST 服务 + SQLite 持久化**，并已落地**核心创作闭环**：资料库（角色/势力/地点/参考文档/作品/关系网）、模型网关真实调用（Ollama 原生 + OpenAI 兼容多厂商 + Claude）、章节流式生成、剧情商讨对话、配置对话自然语言自动入库、世界地图与关系网可视化。

**2026-08-08 落地五大基础模块**（详见 `docs/架构设计-上下文与记忆引擎.md`）：上下文引擎（让 AI 知道该生成什么）、记忆层（章后写后摄取 + 阶段压缩 + 走向卡片）、去 AI 味（前置注入 + 后置纯正则检测）、SKILL 调度（互斥/叠加 + priority 压轴）、全链路接线（生成/商讨走上下文引擎，前端三处最小改动透明化）。
**仍处桩状态的模块**：设定校验、套路模板。

核心交互：对话-centric 布局（底部聊天框，支持 `@角色` `@势力` 快捷输入），顶部标签切换「对话 / 概览 / 角色库 / 势力库 / 地点库 / 伏笔 / 参考文档 / 模型配置」等模块。

---

## 2. 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | Vue 3 + Vite + Element Plus + Pinia + vue-router + axios |
| 后端 | Python + FastAPI + Pydantic v2 + SQLAlchemy 2.0 |
| 数据库 | SQLite（单文件 `C:\Users\w3013\.ai_novel\data\novel_agent.db`，已移出项目目录防 API Key 泄露，无迁移工具） |
| 代理 | 前端 dev server 把 `/api` 代理到 `localhost:8000` |

---

## 3. 目录结构（真实）

```
E:\AI小说创作\
├── README.md                 # 本文件（接力入口）
├── API接口规范.md            # 接口契约（v0.2，含真实/桩状态）
├── PROJECT_REQUIREMENTS.md   # 11 项需求 ↔ 文件落点
├── backend\
│   ├── main.py               # 入口：init_db + 注册全部 router + CORS
│   ├── app\
│   │   ├── core\             # response(信封)/database(引擎+session)/config/gateway(基类+真实厂商适配器)
│   │   ├── schemas\          # Pydantic 模型（每个实体一个文件）
│   │   ├── models\orm.py     # SQLAlchemy ORM（9+ 张表）
│   │   ├── services\         # character_crud / faction_crud / location_crud / project_crud / reference_crud / relation_crud / config_command（真实）；stubs.py（桩）
│   │   └── routers\          # 11 个模块路由
│   └── data\novel_agent.db   # SQLite 数据文件
└── frontend\
    └── src\
        ├── api\              # http.js(实例,自动解包 data) + database.js(crud 助手) + 各模块 api
        ├── store\project.js  # Pinia：作品列表/当前作品/对话
        ├── router\index.js   # 路由（meta.tab=true 的自动出现在顶部标签）
        ├── layout\MainLayout.vue  # 左侧作品树 + 顶部标签
        ├── views\            # ChatView(真)/DatabaseView(真)/FactionView(真)/LocationView(真)/ReferenceView(真)/CharacterRelationView(真)/WorldMapView(真)/ConfigChatView(真)/DirectionView·ForeshadowView·TemplateView(桩UI) / OverviewView
        └── components\workspace\ChatInput.vue  # 聊天输入框（@角色/@势力 快捷输入）
```

---

## 4. 模块实现状态矩阵（最关键）

✅ = 真实持久化 ｜ ⚠️ = 接口桩（占位/mock，待实现）

| 模块 | Router / 文件 | 状态 | 说明 |
| --- | --- | --- | --- |
| 作品管理 | `routers/projects.py` | ✅ | 增删改查真实；列表**分页** |
| 参考文档 | `routers/references.py` | ✅ | 上传文本 / 列表 / 单篇(含正文) / 删除，真实 |
| 角色库 | `routers/database.py` (characters) | ✅ | 11 字段完整 CRUD |
| 势力库 | `routers/database.py` (factions) | ✅ | 完整 CRUD |
| 地点库 | `routers/database.py` (locations) | ✅ | 含 plane/坐标/形状/高度字段 + `geo-relations` 推导方位距离接口 |
| 技能库 | `routers/custom_skill.py` + `services/skill_dispatch.py` + `seed_skills.py` | ✅ | 真实 CRUD + 互斥/叠加调度（priority 压轴）+ 6 条预置 SKILL（startup 幂等安装） |
| 关系网 | `routers/database.py` (relations) + `relation_crud.py` | ✅ | 真实 CRUD + 前端关系网可视化 |
| 设定校验 | `routers/database.py` (validate) | ⚠️ | 占位（`stubs.validate_settings`） |
| 配置对话/指令入库 | `routers/database.py` (command) + `config_command.py` | ✅ | 自然语言抽取角色/势力/地点/关系并 upsert 落库（真实 LLM） |
| 章节生成 | `routers/chapter.py` + `ollama_native` 适配器 | ✅ | SSE 流式 + 消费默认模型真实产出；提示词已收紧（禁英文/思考泄漏） |
| 剧情商讨（对话） | `routers/discussion.py` `/discussion/chat` | ✅ | 流式回复真实（提示词已收紧）；商讨缓存已持久化（GET 返回历史、chat 自动落库、clear/archive 真实） |
| 走向推荐 | 写后摄取 `services/ingestion.py` + `routers/assist.py` | ✅ | 每章生成后推 3 条走向卡片到对话区（可点击续写）；`recommend_global_references` 从全局池荐资料 |
| 模型网关 | `routers/model.py` + `core/gateway` | ✅ | 真实适配器：OpenAI 兼容多厂商(openai/deepseek/qwen/kimi/ernie/spark/siliconflow/zhipu…) + Ollama 原生 `/api/chat` + Claude；支持思考模式开关 |
| 套路模板 | `routers/template.py` | ⚠️ | 占位（`stubs.list_templates` / `generate_outline`） |
| 伏笔 | 上下文引擎 `layer_foreshadow` + 写后摄取 | 🟡 | 上下文集成已真：已落库伏笔可按 `trigger_foreshadow_ids` 注入生成；写后摄取抽取 `foreshadow_actions` 回注。CRUD 路由 `foreshadow.py` 仍桩 |
| 记忆层 / 记忆压缩 | `routers/memory.py` + `services/{memory_crud,ingestion}.py` | ✅ | 章级记忆双表 + 写后摄取 + 阶段压缩（够章数自动触发）+ 全书大事记 + 待确认实体人工回路 |
| 章节列表查询 | `routers/chapter.py` `list_chapters` | ✅ | 真实读取 `chapters` 表（4 级结构按 article 过滤） |

> 图例：✅ = 真实可用 ｜ ⚠️ = 接口桩（占位/mock） ｜ 🟡 = 部分实现（如对话：流式回复真实，但缓存持久化仍桩）。

**前端对应**：ChatView、DatabaseView、FactionView、LocationView、ReferenceView、CharacterRelationView、WorldMapView、ConfigChatView 均为真实可用；DirectionView / ForeshadowView / TemplateView 为占位 UI（后端喂桩数据）。2026-08-08 新增：`ChatPanel.vue` 渲染章后走向卡片（可点击续写）、`GenerateChapterDialog.vue` 加「本次读取 / AI味检测 / 摄取进度」三块透明化面板、`api/assist.js` 封装 AI 辅助端点。

---

## 5. 如何运行（本机实测路径）

### 5.1 后端
> ⚠️ 本项目的 Python 在**项目自带的虚拟环境** `E:\AI小说创作\.venv`（Python 3.12.10），**不是**受管环境 `C:/Users/w3013/.workbuddy/binaries/python/envs/default`，也不是 `backend/.venv`。

```bash
# 虚拟环境（项目自带，已装好依赖：见 backend/requirements.txt）
PYTHON="E:/AI小说创作/.venv/Scripts/python.exe"

cd E:/AI小说创作/backend
# 推荐：用 dev.py 启动（默认关闭 --reload，见下方说明）
$PYTHON dev.py
# 接口文档： http://localhost:8000/docs

# 等价手写（需手动开 reload，沙箱/共享盘环境下不推荐）：
# $PYTHON -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
- ⚠️ **`dev.py` 默认 `reload=False`**（源码 `DEV_RELOAD` 默认 `"0"`，仅 `DEV_RELOAD=1` 才开）：在 `E:\` 共享盘/沙箱下 reload 既不可靠又会拉出关不掉的 8000 孤儿进程（见记忆⑤），故默认关闭。
- ⚠️ **「改后端自动重启」在本环境并不可靠**：后端进程跑在**宿主**、沙箱对 `E:\` 共享盘的文件编辑不触发宿主 uvicorn 的文件监听（共享盘 inotify/polling 失效，且 reload 偶发卡在坏状态）。**改任何后端代码后，必须由用户在宿主侧手动杀 8000 端口进程再重启**（见 §7 环境坑）。
- ✅ **已根治「新 ORM 列报 no such column」**：`core/database.py` 的 `init_db` 启动时自动比对 ORM 与表结构，缺失列自动 `ALTER TABLE ADD COLUMN`（仅覆盖「新增列」；删除/重命名列不在范围内，仍建议另写迁移）。

### 5.2 前端
```bash
cd E:/AI小说创作/frontend
npm install            # 首次
npm run dev            # http://localhost:5173 ，/api 代理到 8000
```
- ✅ **构建坑已根治**：本沙箱把 Node `rmSync` 劫持成不稳定的「安全删除」二进制，原会导致 Vite 清空 `dist/` 那步必崩。已在 `frontend/vite.config.js` 设 `build.emptyOutDir:false`，`npm run build` 现可直接跑通（产出 `dist/`）。部署到无此拦截的环境时可改回 `true`。
- ✅ **已根治「store.xxx is not a function」HMR 坑**：`src/store/project.js` 已接入 `acceptHMRUpdate`，改 store 自动热替换，**无需重启 dev server**。

---

## 6. 约定与契约

- **响应信封**：所有非流式接口返回 `{code:0, message, data, trace_id}`；前端 `api/http.js` 自动解包 `data`。
- **路径前缀**：`/api/v1`；业务路径含 `{project_id}` 做数据隔离。
- **列表返回格式不一致（已知）**：作品列表是分页 `{items,total,...}`；但角色/势力/地点列表返回**纯数组**。`API接口规范.md §0.5` 写的"全部分页"与代码不符，前端 `database.js` 已做兼容（`Array.isArray(res) ? res : res.items`）。
- **错误码 / 统一参数**：见 `API接口规范.md §0.7` 与 `PROJECT_REQUIREMENTS.md §5`。

---

## 7. 环境坑速查（踩过的都记这）

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| `npm run build` 被拦截 / 删文件 | 安全钩子劫持 `rmSync` 清 `dist/` | ✅ 已根治：`vite.config.js` 设 `emptyOutDir:false`，直接 `npm run build` |
| `store.xxx is not a function` | Vite HMR 不重载 Pinia store | ✅ `store/project.js` 已接 `acceptHMRUpdate`，改 store 自动热替换 |
| 改后端无反应（仍跑旧代码/坏状态） | 宿主 uvicorn reload 对共享盘不可靠 | ⚠️ 在宿主侧 `netstat -ano | findstr :8000` 查 PID → `taskkill /PID <PID> /F` → 重启 `python dev.py`（沙箱无法杀宿主进程） |
| 新 ORM 列报 `no such column` | SQLite 不自动迁移 | ✅ `init_db` 启动时自动比对并 `ALTER TABLE ADD COLUMN` 补列 |
| 页面整体偏小 | 浏览器缩放被改（如 50%） | `Ctrl + 0` 恢复 100% |
| `@角色` 下拉空白 | 列表返回纯数组被 `res.items` 解析成空 | `database.js` 已兼容数组 |

---

## 8. 接力开发建议（下一步做什么）

核心闭环（资料库 + 模型网关 + 章节生成 + 对话 + 配置入库 + 世界地图/关系网可视化）**已完成并可运行**。2026-08-08 又落地了上下文引擎 / 记忆层 / 去 AI 味 / SKILL 调度 / 全链路接线（详见 `docs/架构设计-上下文与记忆引擎.md`）。剩余为二期/三期高级功能，均为接口桩，按投入产出比排序：

1. **设定强制校验**：`validate_settings` 生成前校验设定一致性（OOC 目前只靠 SKILL 软约束，未做硬校验）。
2. **套路模板 / 大纲**：`template.py` 内置模板库 + 基于模板+历史摘要拆分大纲。
3. **伏笔 CRUD 路由落地**：上下文集成已真（读取 + 写后抽取 + 生成触发），但 `routers/foreshadow.py` 的增删改查仍是桩，前端 `ForeshadowView` 已就绪。
4. **云端强模型增强**：去 AI 味 `strict` 档（OOC 防护 + 替换表）、模型二次改写链路当前对 4B 关闭，换强模型后可开启。

---

## 9. 一键验证（冒烟测试）

```bash
# 1) 后端存活
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/projects   # 期望 200
# 2) 新建作品
curl -X POST http://localhost:8000/api/v1/projects -H "Content-Type: application/json" \
  -d '{"name":"测试作","genre":"玄幻","summary":"..."}'
# 3) 给该作品建角色
curl -X POST http://localhost:8000/api/v1/projects/<pid>/characters -H "Content-Type: application/json" \
  -d '{"name":"林越","role_type":"主角","personality":"隐忍冷静"}'
# 4) 前端
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/workspace/chat   # 期望 200
```

> ⚠️ 改动任何后端文件后**必须手动重启后端**（本环境 reload 不可靠）；改动 store 后重启前端 dev server。
