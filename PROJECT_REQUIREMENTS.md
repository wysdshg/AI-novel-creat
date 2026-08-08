# 网页小说智能体 — 项目脚手架与落地要求

> 当前阶段：**核心闭环已落地可运行**。网页框架 + 后端 REST + SQLite 已搭好；资料库（角色/势力/地点/参考文档/作品/**关系网**）、模型网关（真实多厂商 + Ollama 原生）、章节流式生成、剧情商讨对话、配置对话自动入库、世界地图/关系网可视化均已真实可用。**仍为接口桩**：设定校验、走向推荐、记忆压缩、伏笔自动化、套路模板、技能库、章节列表查询、商讨缓存持久化。
> 配套文档：`API接口规范.md`（接口契约，含真实/桩状态）、`README.md`（接力上手入口）。
> 技术选型：前端 Vue3 + Element Plus + Vite；后端 Python FastAPI；数据库 SQLite（单文件，无迁移工具）。

---

## 1. 定位与边界

- B/S 网页架构的小说创作专属智能体；模块化解耦、多厂商模型热插拔、结构化资料库、强收敛防 AI 文风、轻量记忆压缩、自然语言指令管理资料库、套路模板可视化、伏笔自动化。
- **本仓库范围**：完整网页 + 分层后端骨架 + 真实持久化的资料库侧（角色/势力/地点/参考文档/作品/关系网）+ 统一响应/分层结构/可扩展骨架 + **真实模型调用（Ollama 原生 + OpenAI 兼容多厂商 + Claude）** + **章节流式生成** + **剧情商讨对话** + **配置对话自动入库**。仍待实现：设定校验算法、记忆压缩算法、伏笔自动识别、走向推演、模板/大纲生成、技能库 CRUD（见 `README.md §4` 状态矩阵）。

## 2. 目录结构

```
E:\AI小说创作\
├── README.md               # 接力上手入口（状态矩阵/运行/环境坑）
├── API接口规范.md          # 接口契约总纲（v0.2，含真实/桩状态）
├── PROJECT_REQUIREMENTS.md # 本文件：需求 ↔ 文件落点
├── backend\                # FastAPI 后端
│   ├── main.py             # 入口，init_db + 注册全部路由 + CORS
│   ├── app\
│   │   ├── core\           # config / response(统一信封) / database(引擎+session) / gateway(基类,未接真实厂商)
│   │   ├── schemas\        # Pydantic 请求/响应模型（每实体一个文件）
│   │   ├── models\orm.py   # SQLAlchemy ORM（9+ 张表，含 geometry/plane 字段）
│   │   ├── services\       # character_crud / faction_crud / location_crud / project_crud / reference_crud（真实）；stubs.py（桩）
│   │   └── routers\        # 11 个模块路由
│   └── data\novel_agent.db # SQLite 数据文件（无迁移工具）
└── frontend\               # Vue3 + Element Plus
    ├── src\
    │   ├── api\            # http.js(实例,自动解包 data) + database.js(crud 助手) + 各模块 api
    │   ├── router\         # 模块路由（meta.tab=true 自动进顶部标签）
    │   ├── layout\         # MainLayout（左侧作品树 + 顶部标签）
    │   ├── store\          # pinia 作品上下文
    │   ├── views\          # ChatView(桩) / DatabaseView(真) / FactionView(真) / LocationView(真) / ReferenceView(真) / 其他(桩或占位)
    │   └── components\     # workspace/ChatInput(@角色/@势力) + database/*Form 等
    ├── vite.config.js      # 含 /api → localhost:8000 代理
    └── package.json
```

## 3. 五层架构 ↔ 代码落点

| 层 | 落点 |
| --- | --- |
| 前端交互层 | `frontend/src/views/*`、`components/*`、Element Plus 表单/弹窗/图谱/时间轴 |
| 指令解析引擎 | 预留于 `backend/app/services/stubs.py` 的 `run_command`（需求10） |
| 核心调度引擎 | 预留 `services`：记忆压缩/设定校验/伏笔检索/走向推演/约束控制器 |
| 多模型 API 网关 | `backend/app/core/gateway/`（`BaseModelAdapter` + `registry` 热插拔）+ `routers/model.py` |
| 持久化数据库层 | `backend/app/models/orm.py`（单作品分表/分 schema 隔离）+ `core/database.py` |

## 4. 11 项需求 ↔ 文件落点

| 需求 | 前端 | 后端路由 | Schema/ORM |
| --- | --- | --- | --- |
| 1 分作品资料库 | DatabaseView | routers/database.py | schemas/database.py, orm |
| 2 单章硬生成 | ChapterView | routers/chapter.py (SSE) | schemas/chapter.py |
| 3 防发散约束 | ChapterView | services 桩（生成控制器） | config.TEMPERATURE |
| 4 设定强制校验 | （生成前弹窗） | /projects/{id}/validate | schemas ValidateResult |
| 5 走向推荐 | DirectionView | routers/direction.py | schemas/direction.py |
| 6 剧情商讨缓存 | DiscussionView | routers/discussion.py | orm DiscussionMessage |
| 7 多厂商网关 | ModelConfigView | routers/model.py + gateway | schemas/model.py |
| 8 记忆压缩 | （后台） | routers/memory.py | schemas/memory.py |
| 9 伏笔自动化 | ForeshadowView + Timeline | routers/foreshadow.py | schemas Foreshadow |
| 10 指令自动入库 | 指令输入框 | /projects/{id}/command | CommandRequest |
| 11 套路模板 | TemplateView + Dialog | routers/template.py | schemas/template.py |

## 5. 统一约定（开发必须遵守）

- **响应信封**：`{code,message,data,trace_id}`，成功 `code:0`（见 `core/response.py`）。
- **路径**：`/api/v1` 前缀；业务路径含 `{project_id}` 实现数据隔离。
- **温度**：章节 0.4 / 走向 0.7 / 记忆 0.2 / 解析 0.3 / 伏笔 0.5（`core/config.py`）。
- **章节**：单次单章，3000–5000 字（`config.CHAPTER_WORD_*`）。
- **流式**：章节生成为 SSE，事件 `start/chunk/validate/done/error`（前端 `api/chapter.js` 已封装 `generateChapterStream`）。
- **错误码**：见 `API接口规范.md §0.7`。

## 6. 如何运行（本机实测路径）

> 详见 `README.md §5`。以下为要点。

### 后端
```bash
# 受管虚拟环境（已装依赖），不是 backend/.venv
PYTHON="C:/Users/w3013/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
cd E:/AI小说创作/backend
$PYTHON -m uvicorn main:app --host 127.0.0.1 --port 8000
# 文档： http://localhost:8000/docs
```
> ⚠️ `dev.py` 虽默认 `reload=True`，但本环境宿主 uvicorn 对共享盘编辑**不可靠触发**重载；改后端后仍需在宿主侧手动杀 8000 端口进程再重启。SQLite 无迁移，新增 ORM 列靠 `init_db` 自动 `ALTER TABLE ADD COLUMN`（仅新增列）。

### 前端
```bash
cd E:/AI小说创作/frontend
npm install
npm run dev      # http://localhost:5173 （/api 代理到 8000）
```
> ⚠️ 验证编译用 `npm run build -- --outDir dist-test --emptyOutDir false`（默认清 dist 会被安全钩子拦截）。
> ⚠️ 改 Pinia store 后需重启 dev server（Vite HMR 不重载 store）。

## 7. 可扩展性（关键）

- **新增业务模块**：`backend/app/routers/` 新建路由 → `main.py` 注册；`frontend/src/api/` 新建调用 → `views/` 新建页面 → `router/index.js` 加路由。（详见 API接口规范.md §10）
- **新增模型厂商**：仅实现 `core/gateway/base.py: BaseModelAdapter` 子类，在 `registry.py` 注册 `vendor` 字符串，引擎层零改动。
- **前端解耦**：所有后端调用集中在 `src/api/*`；视图通过 `props/emits` 暴露边界；可视化组件（图谱/时间轴）独立接收标准 Schema。

## 8. 阶段规划（对应设计文档第四节）

| 期 | 内容 | 当前状态 |
| --- | --- | --- |
| 一期 | 资料库（角色/势力/地点/参考文档）、作品管理、统一骨架 | ✅ 已落地（作品/参考文档/角色/势力/地点真实；**关系网**也已真实；技能仍为桩） |
| 二期 | 记忆压缩、伏笔、设定校验、商讨缓存、走向推荐 | 接口桩就绪（未实现）；商讨**对话**已真实，仅缓存持久化仍桩 |
| 三期 | 章节流式生成、对话持久化、关系图谱、模板组件、前端交互闭环 | ✅ 核心闭环已打通（章节生成/对话/关系图谱/世界地图/配置入库均真实）；模板组件仍桩 |
| 四期 | 文风 LoRA、RAG、多人协同、真实多厂商网关 | 多厂商网关已落地（Ollama 原生 + OpenAI 兼容 + Claude）；LoRA/RAG/协同为预留扩展点 |
