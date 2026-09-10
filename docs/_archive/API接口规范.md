# 网页小说智能体 — API 接口规范（接口要求文档）

> 版本：**v0.4（2026-08-14）**
> 本轮变更：新增 4 级结构（卷/篇）、全局漫游对话（global-chat）、全局参考资料池、AI辅助能力层（去AI味扫描/SKILL调度/实体确认/设定校验接口）、小说绑定设定库；修正工作流 alias、删除级联、参考目录传参等已知 bug。
> 适用范围：B/S 架构小说创作专属智能体，对应顶层五层架构中的「指令解析引擎 / 核心调度引擎 / 多模型 API 网关 / 持久化数据库层」对外暴露部分。
> 读者：前端开发者、后端开发者、接入第三方模型厂商的开发者。

---

## 0. 文档定位与约定

本文件是**接口契约总纲**。开发**必须**遵守本文档定义的路径、方法、入参、出参与错误码。

> ⚠️ 每个章节标题后标注 [✅真实] / [⚠️桩] / [🟡部分] 表示当前实现状态，与代码逐一核对（最后核对 2026-08-14）。

### 0.1 实现状态矩阵（真实 / 桩）

| 章节 | 模块 | 状态 |
| --- | --- | --- |
| §1 | 作品 Project | ✅ 真实（列表分页 + 绑定设定库） |
| §1.5 | 4 级结构（卷/篇/章） | ✅ 真实（删卷/删篇级联删除子数据） |
| §2.1 | 角色 Characters | ✅ 真实（11 字段） |
| §2.2 | 技能 Skills（角色技能） | ✅ 真实 |
| §2.3 | 关系 Relations | ✅ 真实 |
| §2.4 | 势力 Factions | ✅ 真实 |
| §2.4b | 地点 Locations | ✅ 真实（含 geometry/plane + geo-relations） |
| §2.6 | 设定校验 validate | ⚠️ 桩 |
| §2.7 | 指令入库 command | ✅ 真实（自然语言抽取 + dry_run 预览） |
| §3.1 | 剧情商讨 Discussion | ✅ 真实（持久化 + 会话线程） |
| §3.1b | 全局漫游对话 global-chat | ✅ 真实（`__global__` 线程 + conversation_id 隔离会话） |
| §3.2 | 章节生成 Chapter | ✅ 真实（SSE 流式；未配模型不覆盖正文） |
| §4 | 模型网关 Model | ✅ 真实 |
| §5 | 记忆压缩 Memory | ✅ 真实（ingest/compress/summary/stages/events/pending-entities） |
| §5b | AI 辅助 Assist | ✅ 真实（humanize scan / skills dispatch / config / confirm-entities / polish / aggregate-overview） |
| §6 | 伏笔 Foreshadow | ⚠️ CRUD 桩；上下文注入与写后抽取真实 |
| §7 | 走向推荐 Direction | 🟡 GET 空数组 / POST 桩；实际走向由写后摄取推卡片 |
| §8 | 套路模板 Template | ⚠️ 桩 |
| §11 | 参考文档 Reference Doc | ✅ 真实（含 catalog 按需加载） |
| §11b | 全局参考资料 | ✅ 真实（CRUD + catalog + import-global） |
| §12 | 全局设定库 Setting | ✅ 真实 |
| §13 | 全局写作 SKILL CustomSkill | ✅ 真实 |
| §14 | 工作流 Workflow | ✅ 真实（from/from_ alias 已修复） |

### 0.2 列表返回格式差异（已知不一致）

- 作品列表：**分页** `{items, total, page, page_size}`（见 §0.5）。
- 角色 / 势力 / 地点 / 设定 / SKILL / 工作流列表：**纯数组**（非分页）。
- 前端 `api/*` 已兼容两种格式。
- 新增列表接口时请统一为分页格式，并同步更新此处说明。

### 0.8 基础 URL

| 环境 | Base URL |
| --- | --- |
| 本地开发 | `http://localhost:8000/api/v1` |
| 生产 | 由 Nginx 反代，前缀同 `/api/v1` |

> 所有路径**不带**尾部斜杠。版本号固定在路径中（`/api/v1`），便于未来 `/api/v2` 灰度。

### 0.3 通用请求约定

- 内容类型：`application/json; charset=utf-8`。
- 时间字段统一 ISO-8601 字符串。
- 编码：UTF-8。
- 资源标识：`project_id`（字符串 UUID 或 `__global__`）、各实体 `id`（字符串）。

### 0.4 鉴权（占位，待定）

当前**不启用鉴权**，所有端点匿名可访问。生产建议 `Authorization: Bearer <token>` + `project_id` 归属隔离。

### 0.5 统一响应信封（Envelope）

所有非流式端点返回统一结构：

```json
{ "code": 0, "message": "success", "data": { }, "trace_id": "a1b2c3d4" }
```

`code`：`0` 成功；非 0 见 §0.7。`data`：业务数据。

### 0.6 分页约定

作品列表返回 `{items, total, page, page_size}`。其余列表返回纯数组。

### 0.7 流式端点（章节生成 / 商讨）

使用 `text/event-stream`（SSE）。事件格式统一：

```
event: <name>
data: {json}
```

### 0.8 错误码表

| code | HTTP | 含义 | 前端建议 |
| --- | --- | --- | --- |
| 0 | 200 | 成功 | — |
| 40001 | 400 | 参数校验失败 | 高亮表单字段 |
| 40002 | 400 | 指令无法解析 | 提示用户改写指令 |
| 40301 | 403 | 无权限访问该作品 | 跳转无权限页 |
| 40401 | 404 | 资源不存在 | 提示并刷新列表 |
| 40901 | 409 | 数据冲突（如重复角色名） | 提示冲突项 |
| 42201 | 422 | 设定校验未通过 | 展示高亮问题 |
| 42901 | 429 | 模型网关限流 | 提示稍后重试 |
| 50001 | 500 | 服务端内部错误 | 上报 trace_id |
| 50101 | 501 | 接口未实现 | 展示"功能开发中" |
| 50301 | 503 | 所有模型厂商不可用 | 提示切换备用模型 |

---

## 1. 作品（项目）隔离模型 [✅真实]

每本小说为独立「作品（project）」。所有业务实体含 `project_id` 字段（`SettingORM` / `CustomSkillORM` / `WorkflowORM` 为全局共享，无此字段）。

### 1.1 端点（`routers/projects.py` + `project_crud.py`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/projects` | 新建作品 |
| GET | `/projects` | 作品列表（分页，附 chapter_count） |
| GET | `/projects/{project_id}` | 详情 |
| PUT | `/projects/{project_id}` | 修改元信息 |
| DELETE | `/projects/{project_id}` | 删除（级联清空该作品 15 张业务表，含卷/篇/章/参考/记忆/阶段摘要/加载日志） |
| GET | `/projects/{project_id}/settings` | 返回该小说绑定的设定库 ID 列表 |
| PUT | `/projects/{project_id}/settings` | 全量替换绑定设定库；`setting_ids=null` = 全量注入（向后兼容）；校验所有 ID 合法 |

### 1.2 作品实体 Schema

```json
{
  "id": "uuid", "name": "苍穹剑歌", "genre": "玄幻", "summary": "...",
  "status": "draft|writing|paused|finished",
  "db_backend": "sqlite|mysql",
  "setting_ids": ["uuid", "..."],
  "chapter_count": 12,
  "created_at": "ISO", "updated_at": "ISO"
}
```

---

## 1.5 4 级结构：小说 → 卷 → 篇 → 章 [✅真实]

- 章挂在篇下，篇挂在卷下；`ChapterORM.article_id`、`ArticleORM.volume_id` 均冗余 `project_id` 便于整本查询。
- 删除级联（**已修复**）：删章删记忆/伏笔动作关联；删篇先删其下章；删卷先删其下篇及其章；删小说清全部。

### 1.5.1 卷（`routers/volume.py` + `volume_crud.py`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/projects/{project_id}/volumes` | 卷列表 |
| POST | `/projects/{project_id}/volumes` | 新建卷 |
| GET | `/projects/{project_id}/volumes/{volume_id}` | 详情 |
| PUT | `/projects/{project_id}/volumes/{volume_id}` | 修改 |
| DELETE | `/projects/{project_id}/volumes/{volume_id}` | 删除（级联删篇+章） |

### 1.5.2 篇（`routers/article.py` + `article_crud.py`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/projects/{project_id}/articles` | 篇列表（支持 `?volume_id=`） |
| POST | `/projects/{project_id}/volumes/{volume_id}/articles` | 在卷下新建篇 |
| GET | `/projects/{project_id}/articles/{article_id}` | 详情 |
| PUT | `/projects/{project_id}/articles/{article_id}` | 修改（可换卷，校验目标卷属于同 project） |
| DELETE | `/projects/{project_id}/articles/{article_id}` | 删除（级联删章） |
| GET | `/articles/{article_id}/chapters` | 篇下章节列表 |
| POST | `/articles/{article_id}/chapters` | 篇下建章（`ChapterCreate`） |

**篇 Schema**：`id, volume_id, project_id, name, summary, sort_order, created_at, updated_at`

---

## 2. 模块 1：分作品资料库系统

基础路径：`/projects/{project_id}`（`routers/database.py`）

### 2.1 角色表（Characters）[✅真实]

POST/GET/GET/PUT/DELETE `/characters`、`/characters/{character_id}`；支持 `?name=&tag=` 过滤。

**Schema**：`id, name, appearance, personality, background, talent, experience, status, skill_ids[], faction_id, tags[], created_at, updated_at`

### 2.2 技能表（Skills·角色技能）[✅真实]

POST/GET/GET/PUT/DELETE `/skills`、`/skills/{skill_id}`；删除级联解除角色绑定。

**Schema**：`id, project_id, name, level, effect, limitation, owner_id, side_effect, unlock_condition`

### 2.3 关系网表（Relations）[✅真实]

POST/GET/PUT/DELETE `/relations`、`/relations/{relation_id}`；列表支持 `?character_id=`。

**Schema**：`id, subject_id, object_id, relation_type, strength(0-100), note`

### 2.4 势力表（Factions）[✅真实]

POST/GET/GET/PUT/DELETE `/factions`、`/factions/{faction_id}`。

**Schema**：`id, name, description, leader_id, members[], status`

### 2.4b 地点表（Locations）[✅真实]

POST/GET/GET/PUT/DELETE `/locations`、`/locations/{location_id}`；GET `/locations/{location_id}/geo-relations` 推导同 plane 且双侧有坐标地点的 `{bearing(8方位), distance, height_diff}`。

**Schema**：`id, name, location_type, region, description, notable_features[], related_ids[], plane, center_x, center_y, shape(point|circle|rect|sector|polygon), radius, radius_y, angle, angle_span, height, polygon`

### 2.5 资料库双配置模式

- 手动：前端表单直接调 §2.1–2.4 CRUD。
- AI 自动：见 §2.7 指令入口，`dry_run=true` 预览 → 审核 → 落库。

### 2.6 设定强制校验 [⚠️桩]

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/projects/{project_id}/validate` | 返回 `constraint_list` + `issues[]`（桩，`stubs.validate_settings` 占位） |

### 2.7 对话指令自动入库 [✅真实]

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/projects/{project_id}/command` | `{"text":"...", "dry_run": false}`；真实 LLM 抽取角色/势力/地点/关系并 upsert |

- `dry_run=true`：返回将执行变更预览，不落库。
- 引擎 `services/config_command.py::run`；失败返回 `40002`。

---

## 3. 模块 2/3：剧情商讨 + 章节生成 [✅真实]

### 3.1 剧情商讨会话缓存池（`routers/discussion.py` + `discussion_crud.py`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/projects/{project_id}/discussion` | 历史消息（`?chapter_id=&conversation_id=`） |
| POST | `/projects/{project_id}/discussion/messages` | 追加一条消息（不调模型） |
| DELETE | `/projects/{project_id}/discussion` | 清空线程 |
| POST | `/projects/{project_id}/discussion/archive` | 归档为指定章节备注 |
| POST | `/projects/{project_id}/discussion/chat` | 流式商讨（SSE） |

**线程优先级**：`conversation_id` > `chapter_id` > 小说级默认线程。写入/读取侧已对称（章级强制 conversation_id=null）。

**消息 Schema**：`id, project_id, role(user|assistant), content, thinking, meta, chapter_id, conversation_id, created_at`

### 3.1b 全局漫游对话 [✅真实]

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/discussion/global-chat` | 未选小说通用问答；注入全局设定库目录 + 全局 SKILL + 全局参考目录；按 `conversation_id` 隔离多个漫游会话 |
| GET | `/discussion/load-logs` | P0 观测：本轮实际加载了哪些设定/参考（`?project_id=&limit=`） |

body 可携带 `conversation_id`；用户消息与 AI 回复均落在对应会话线程。

### 3.2 章节生成 [✅真实]

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/projects/{project_id}/chapters/generate` | 单章流式生成（SSE） |
| POST | `/projects/{project_id}/chapters` | 非流式落库 |
| GET | `/projects/{project_id}/chapters` | 列表（`?article_id=` 过滤） |
| GET | `/projects/{project_id}/chapters/{chapter_id}` | 详情 |
| PUT | `/projects/{project_id}/chapters/{chapter_id}` | 修改 |
| DELETE | `/projects/{project_id}/chapters/{chapter_id}` | 删除 |

**生成请求体（`GenerateRequest`）**：

```json
{
  "chapter_no": 13,
  "prompt_hint": "林越夜探藏剑阁",
  "from_discussion": true,
  "trigger_foreshadow_ids": ["fs_01"],
  "word_range": {"min":3000,"max":5000},
  "temperature": 0.75,
  "enable_thinking": true,
  "article_id": "uuid",
  "title": "可选（用则覆盖标题）",
  "chapter_id": "uuid（可选；非空=覆盖该章重新生成）",
  "thread_chapter_id": "uuid（生成时所在章线程）",
  "thread_conversation_id": "可选",
  "ingest": true
}
```

**关键行为**：
- `chapter_id` 非空 → 覆盖原章（保持章号，不新建）。
- `use_model=False`（未配置可用模型）时：**若指定 `chapter_id`，不覆盖原正文**，发提示并结束流；未指定则占位文本落库。
- 写后摄取挪到后台线程（`threading.Thread`），不阻塞 SSE。

### 3.3 生成流式事件（SSE）

`start` → `context`（元信息） → `refs`（可选，额外加载参考） → `chunk` → `validate`（AI味检测） → `saved` → `ingest_start` → `done`

```
event: start    data: {"chapter_no":13}
event: chunk    data: {"text":"夜色如墨…"}
event: validate data: {"issues":[],"score":0.12}
event: saved    data: {"chapter_id":"...","word_count":4180}
event: done     data: {"chapter_id":"...","word_count":4180}
```

异常事件：`stopped`（复读检测截断，`{"reason":"detected_repetition"}`）。

---

## 4. 模块 4：多厂商统一 API 网关 [✅真实]

### 4.1 端点（`routers/model.py`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/models` | 列表（api_key 掩码 `***后4位`） |
| GET | `/models/{model_id}` | 详情（**完整 api_key**，仅本地） |
| POST | `/models` | 新增配置 |
| PUT | `/models/{model_id}` | 修改（api_key 空串=保留原值） |
| DELETE | `/models/{model_id}` | 删除 |
| POST | `/models/{model_id}/set-default` | 设为默认（全局唯一） |
| POST | `/models/test` | 真实请求厂商接口测连通性 |

### 4.2 模型配置 Schema

`id, name, vendor(deepseek|qwen|ernie|spark|kimi|openai|claude|ollama|custom), api_base, api_key, model_name, context_window, temperature, top_p, max_tokens, role(primary|memory|parse|foreshadow), is_backup, status(active|disabled), is_default`

### 4.3 适配器扩展接口

`backend/app/core/gateway/`：
- `base.py::BaseModelAdapter`（ABC：chat / stream / astream / test_connection）
- `registry.py::register(vendor)` / `get_adapter(vendor, config)`；未注册厂商回退 `PlaceholderAdapter`
- `adapters/openai_compat.py`（OpenAI 兼容多厂商）
- `adapters/claude.py`（Anthropic `/v1/messages`）
- `adapters/ollama_native.py`（`/api/chat`，`repeat_penalty`、动态 `num_ctx`，章节默认走此）

**新增厂商** = 继承 `BaseModelAdapter` + `register(vendor)(Cls)`，引擎层零改动。

---

## 5. 模块 5：篇章记忆与压缩 [✅真实]（`routers/memory.py` + `memory_crud.py` + `ingestion.py`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/projects/{project_id}/memory/ingest/{chapter_id}` | 对指定章重跑写后摄取（记忆+摘要+走向） |
| GET | `/projects/{project_id}/memory/chapters` | 章级记忆列表（`?article_id=`） |
| GET | `/projects/{project_id}/memory/chapters/{chapter_id}` | 单章记忆 |
| DELETE | `/projects/{project_id}/memory/chapters/{chapter_id}` | 删除章记忆 |
| POST | `/projects/{project_id}/memory/compress` | 手动压缩 `from_no~to_no` 为阶段摘要 |
| GET | `/projects/{project_id}/memory/stages` | 阶段摘要列表 |
| GET | `/projects/{project_id}/memory/summary` | 总览：stages + recent(5) + count |
| GET | `/projects/{project_id}/memory/events` | 全书大事记（plot_points 铺开） |
| GET | `/projects/{project_id}/memory/pending-entities` | 待确认新实体（人工回路） |

**章级记忆 Schema**：`id, project_id, chapter_id, chapter_no, title, plot_points[], character_states[], new_entities[], foreshadow_actions[], summary, status`

---

## 5b. AI 辅助能力层 [✅真实]（`routers/assist.py`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/humanize/scan` | 纯正则 AI 味扫描（`ScanRequest`） |
| GET | `/humanize/prompt` | 获取去 AI 味提示词块（`?scene=&level=`） |
| POST | `/projects/{project_id}/chapters/{chapter_id}/scan` | 对已存章节扫描并落库报告 |
| GET | `/skills/dispatch` | SKILL 调度结果（`?trigger=`） |
| POST | `/skills/seed` | 幂等安装/覆盖预置 SKILL（`?overwrite=`） |
| GET | `/config` | 读全局配置（AppConfigORM） |
| PUT | `/config` | 写全局配置（记忆 N / 扫描开关等，`KEY_*` 见 `app_config.py`） |
| GET | `/projects/{project_id}/references/recommend` | 从全局池按正文相关性荐参考（`?top_k=`） |
| POST | `/projects/{project_id}/memory/confirm-entities` | 实体确认入库：`{chapter_id, items[]}`，重名跳过，返回 `{created[], skipped[]}` |
| POST | `/projects/{project_id}/llm/polish-element` | LLM 单元素润色改写（角色/地点/势力描述） |
| POST | `/projects/{project_id}/aggregate-overview` | 递归聚合篇/卷记忆为概览文本（内部 LLM） |

---

## 6. 模块 6：伏笔线索自动化管理 [⚠️CRUD桩 / 上下文真实]

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST/GET/PUT/DELETE | `/projects/{project_id}/foreshadows`、`/{foreshadow_id}` | CRUD（**桩**，返回占位） |
| POST | `/projects/{project_id}/foreshadows/detect` | AI 识别伏笔（**桩**） |
| GET | `/projects/{project_id}/foreshadows/active` | 可触发伏笔清单（**桩**） |
| POST | `/projects/{project_id}/foreshadows/{foreshadow_id}/activate` | 标记回收（**桩**） |

> 真实能力在上下文引擎：`layers.py::layer_foreshadows` 把 pending 伏笔注入生成；写后摄取 `ingestion.py` 抽取 `foreshadow_actions` 回注。CRUD 落地是最大待办。

**伏笔 Schema**：`id, project_id, buried_chapter, description, scene, trigger_condition, enabled, activated_chapter, related_ids[], status(pending|active|done)`

---

## 7. 模块 7：剧情走向推荐 [🟡部分]

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/projects/{project_id}/chapters/{chapter_id}/directions` | 推演走向（**桩**，`stubs`） |
| GET | `/projects/{project_id}/chapters/{chapter_id}/directions` | 走向列表（当前返回 `[]`） |
| POST | `/projects/{project_id}/directions/{direction_id}/select` | 选中走向入商讨（**桩**） |

> 实际走向卡片由写后摄取 `ingestion.py::ingest_chapter` 生成并推送到被生成**章自己的对话线程**（`_render_directions`）。

---

## 8. 模块 8：小说套路模板 [⚠️桩]

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/templates` | 模板库列表（桩） |
| POST | `/projects/{project_id}/templates/{template_id}/outline` | 生成大纲（桩） |
| GET/POST/PUT/DELETE | `/projects/{project_id}/outlines`、`/outlines/{outline_id}` | 大纲 CRUD（桩） |

---

## 9. 全局参考三库（需求 12/13/14，跨小说复用）

### 9.1 全局设定库 Setting [✅真实]（`routers/setting.py`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/settings` | 列表（`?category=&keyword=&template_only=`） |
| POST | `/settings` | 新建 |
| GET | `/settings/{setting_id}` | 详情 |
| PUT | `/settings/{setting_id}` | 修改 |
| DELETE | `/settings/{setting_id}` | 删除 |

**Schema**：`id, name, category(境界/货币/体系/规则/其它), levels[], description, tags[], is_template, created_at, updated_at`

> 注入：小说 `setting_ids` 绑定后，商谈/生成时经 `layers.build_setting_catalog` 生成为目录，AI 可 `LOAD_SETTING:<id>` 按需拉取正文。

### 9.2 全局写作 SKILL [✅真实]（`routers/custom_skill.py` + `skill_dispatch.py`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/global-skills` | 列表（`?trigger=&enabled_only=&keyword=`） |
| POST | `/global-skills` | 新建 |
| GET | `/global-skills/{skill_id}` | 详情 |
| PUT | `/global-skills/{skill_id}` | 修改 |
| DELETE | `/global-skills/{skill_id}` | 删除 |

**Schema**：`id, name, description, prompt_body, trigger(discussion|chapter|memory|parse|all), enabled, tags[], created_at, updated_at`

> 调度：`skill_dispatch.collect` 按 trigger 分组；`priority` 数值大者优先，互斥类仅留最高；`all` 全阶段注入。startup 幂等安装 6 条预置。

### 9.3 全局工作流 Workflow [✅真实]（`routers/workflow.py` + `workflow_crud.py`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/workflows` | 列表（`?active_only=&keyword=`） |
| POST | `/workflows` | 新建（DAG 端点校验） |
| GET | `/workflows/{wf_id}` | 详情 |
| PUT | `/workflows/{wf_id}` | 修改 |
| DELETE | `/workflows/{wf_id}` | 删除 |
| POST | `/workflows/{wf_id}/duplicate` | 复制（id 重生，name 加"(副本)"） |

**Schema**：`id, name, description, nodes[{id,type,label,params,position}], edges[{from,to,condition}], tags[], is_active, created_at, updated_at`

> ⚠️ 已知坑（已修）：`FlowEdge.from_`（alias `from`）读写必须 `by_alias=True`；历史脏数据 `from_` 键读取时会归一化。

---

## 10. 参考资料（按小说 + 全局池）[✅真实]

### 10.1 按小说参考（`routers/references.py`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/projects/{project_id}/references` | 上传（auto_summary 自动摘要 + auto_tags） |
| GET | `/projects/{project_id}/references` | 列表（不含正文） |
| GET | `/projects/{project_id}/references/catalog` | 目录（`?include_global=`，含 locked 标记） |
| GET | `/projects/{project_id}/references/{doc_id}` | 详情（含正文） |
| PUT | `/projects/{project_id}/references/{doc_id}` | 重命名 |
| DELETE | `/projects/{project_id}/references/{doc_id}` | 删除 |

### 10.2 全局参考池（`routers/reference_global.py`）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/references/global` | 全局池列表 |
| GET | `/references/global/catalog` | 全局目录（按需加载用） |
| POST | `/references/global` | 上传全局资料 |
| GET | `/references/global/{doc_id}` | 详情 |
| PUT | `/references/global/{doc_id}` | 重命名 |
| DELETE | `/references/global/{doc_id}` | 删除 |
| POST | `/projects/{project_id}/references/import-global` | 把选中全局资料复制进小说（`{doc_ids:[]}`） |

### 10.3 参考加载协议（SSE 对话内）

AI 判断需要某资料时，**只输出一行**然后停止，后端注入正文后让其续答：

```
LOAD_REFS:<id1>,<id2>
LOAD_SETTING:<id1>,<id2>
```

解析与取正文：`reference_crud.parse_load_refs` / `parse_load_setting` / `fetch_refs_by_ids` / `fetch_settings_by_ids`。

### 10.4 章节相关性选参（`reference_crud.pick_relevant`）

生成章节时按 `query_text + 已识别的实体名` 打分（`score_reference`），默认 `top` 取相关性最高若干份；`NA_CHAPTER_REF_MODE=hybrid` 开启 AI 额外选装。

---

## 11. 待定 / 后续补全

- 鉴权与多租户（§0.4）；
- 文件/图片上传（封面、图谱导出）；
- 限流策略具体参数；
- 审计日志表结构细化；
- 工作流执行引擎（§14.3 TODO）；
- SKILL 运行时扩展点（cooldown 等）；
- **桩模块落地**：设定校验（§2.6）、伏笔 CRUD（§6）、走向推荐（§7）、套路模板（§8）。

> 本文档随开发推进持续修订，版本号递增。任何偏离本规范的设计须先更新本文档再编码。