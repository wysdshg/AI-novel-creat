# 网页小说智能体 — API 接口规范（接口要求文档）

> 版本：**v0.3（本轮：新增 §12 设定库 / §13 写作 SKILL / §14 工作流，§2.2 技能升为真实）**
> 适用范围：B/S 架构小说创作专属智能体。对应顶层五层架构中的「指令解析引擎 / 核心调度引擎 / 多模型 API 网关 / 持久化数据库层」对外暴露部分。
> 读者：前端开发者、后端开发者、接入第三方模型厂商的开发者。
> 最后更新：2026-08-08

---

## 0. 文档定位与约定

本文件是**接口契约总纲**。开发**必须**遵守本文档定义的路径、方法、入参、出参与错误码。

> ⚠️ **重要：本文档 v0.1 曾称"所有接口均为桩"。现已过时。** 截至 v0.3，作品/参考文档/角色/势力/地点/技能/设定库/全局SKILL/工作流/章节生成/剧情商讨/模型网关/记忆压缩/指令入库均已落地真实持久化；仅**设定校验、套路模板、伏笔 CRUD、走向推荐(POST)仍为桩**。每个章节标题后标注 [✅真实] / [⚠️桩] / [🟡部分] 表示当前实现状态，详见 §0.1 状态矩阵。

### 0.1 实现状态矩阵（真实 / 桩）

| 章节 | 模块 | 状态 |
| --- | --- | --- |
| §1 | 作品 Project | ✅ 真实（列表分页） |
| §2.1 | 角色 Characters | ✅ 真实（11 字段） |
| §2.2 | 技能 Skills | ✅ 真实（本轮升，原为 ⚠️桩） |
| §2.3 | 关系 Relations | ✅ 真实 |
| §2.4 | 势力 Factions | ✅ 真实 |
| §2.4b | 地点 Locations | ✅ 真实（含 geometry/plane + geo-relations） |
| §2.6 | 设定校验 validate | ⚠️ 桩 |
| §2.7 | 指令入库 command | ✅ 真实（自然语言抽取角色/势力/地点/关系并 upsert 落库） |
| §3.1 | 剧情商讨 Discussion | ✅ 真实（持久化） |
| §3.2 | 章节生成 Chapter | ✅ 真实（SSE 流式，消费默认模型 / Ollama 原生适配器产出） |
| §4 | 模型网关 Model | ✅ 真实 |
| §5 | 记忆压缩 Memory | ✅ 真实（ingest / compress / summary / stages / events / pending-entities 全落地） |
| §6 | 伏笔 Foreshadow | ⚠️ 桩 |
| §7 | 走向推荐 Direction | 🟡 部分（GET 列表真实；POST 推荐仍桩，靠写后摄取推卡片） |
| §8 | 套路模板 Template | ⚠️ 桩 |
| §11 | 参考文档 Reference Doc | ✅ 真实 |
| §12 | 设定库 Setting | ✅ 真实（本轮新增） |
| §13 | 写作 SKILL CustomSkill | ✅ 真实（本轮新增） |
| §14 | 工作流 Workflow | ✅ 真实（本轮新增） |

### 0.2 列表返回格式差异（已知不一致）

- 作品列表：**分页** `{items, total, page, page_size}`（见 §0.5）。
- 角色 / 势力 / 地点列表：**纯数组**（非分页）。
- 前端 `api/database.js` 已兼容两种格式：`Array.isArray(res) ? res : (res.items || [])`。
- 新增列表接口时请统一为分页格式，并同步更新此处说明。



### 0.8 基础 URL

| 环境 | Base URL |
| --- | --- |
| 本地开发 | `http://localhost:8000/api/v1` |
| 生产 | 由 Nginx 反代，前缀同 `/api/v1` |

> 所有路径**不带**尾部斜杠。版本号固定在路径中（`/api/v1`），便于未来 `/api/v2` 灰度。

### 0.2 通用请求约定

- 内容类型：`application/json; charset=utf-8`（文件上传类见各端点说明）。
- 时间字段统一 ISO-8601 字符串（如 `2026-08-06T14:53:55+08:00`）。
- 编码：UTF-8。
- 资源标识：`project_id`（作品 ID，字符串 UUID）、各实体 `id`（字符串 UUID 或数据库自增，统一以字符串返回）。

### 0.3 鉴权（占位，待定）

当前脚手架**不启用鉴权**，所有端点匿名可访问。生产环境建议：

- Header：`Authorization: Bearer <token>`
- 多用户部署时在 `project_id` 维度做数据归属隔离（见 §1）。

> 扩展点：在 `backend/app/core/security.py` 预留 `get_current_user` 依赖，后续接入即可。

### 0.4 统一响应信封（Envelope）

所有非流式端点返回统一结构：

```json
{
  "code": 0,
  "message": "success",
  "data": { },
  "trace_id": "a1b2c3d4"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | int | `0` 成功；非 0 见 §0.7 错误码 |
| `message` | string | 人类可读提示 |
| `data` | any | 业务数据；列表类见 §0.5 分页包装 |
| `trace_id` | string | 链路追踪 ID，排障用 |

### 0.5 分页约定

列表类端点支持 `page`（默认 1）、`page_size`（默认 20，最大 100）、`order_by`、`desc`。返回 `data` 包装为：

```json
{
  "code": 0,
  "data": {
    "items": [ {}, {} ],
    "total": 42,
    "page": 1,
    "page_size": 20
  }
}
```

### 0.6 流式端点（章节生成）

章节生成为**流式**接口，使用 `WebSocket` 或 `text/event-stream`（SSE）。本规范**首选 SSE**（实现简单、天然断线重连）。事件类型见 §4。

### 0.7 错误码表

| code | HTTP | 含义 | 前端建议 |
| --- | --- | --- | --- |
| 0 | 200 | 成功 | — |
| 40001 | 400 | 参数校验失败 | 高亮表单字段 |
| 40002 | 400 | 指令无法解析（自然语言指令识别失败） | 提示用户改写指令 |
| 40301 | 403 | 无权限访问该作品 | 跳转无权限页 |
| 40401 | 404 | 资源不存在 | 提示并刷新列表 |
| 40901 | 409 | 数据冲突（如重复角色名） | 提示冲突项 |
| 42201 | 422 | 设定校验未通过（角色崩坏/技能乱用） | 展示高亮问题 |
| 42901 | 429 | 模型网关限流/配额耗尽 | 提示稍后重试 |
| 50001 | 500 | 服务端内部错误 | 上报 trace_id |
| 50101 | 501 | 接口未实现（脚手架阶段常态） | 展示"功能开发中" |
| 50301 | 503 | 所有模型厂商不可用 | 提示切换备用模型 |

---

## 1. 作品（项目）隔离模型 [✅真实]

对应需求 1、4、10 的数据隔离。每本小说为独立「作品（project）」，其下数据表（角色/技能/关系/势力/伏笔/章节）**逻辑隔离**：

- 单机 SQLite：每作品独立 schema 或表前缀 `p_<project_id>_*`；
- 多人 MySQL：每作品独立数据库或 schema。
- 所有业务端点路径均含 `{project_id}`，缺失或无权访问返回 `40301/40401`。

### 1.1 端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/projects` | 新建作品（自动初始化隔离数据表） |
| GET | `/projects` | 作品列表（分页） |
| GET | `/projects/{project_id}` | 作品详情 |
| PUT | `/projects/{project_id}` | 修改作品元信息（名称/简介/类型） |
| DELETE | `/projects/{project_id}` | 删除作品（级联清空其数据表） |

### 1.2 作品实体 Schema

```json
{
  "id": "uuid",
  "name": "苍穹剑歌",
  "genre": "玄幻",
  "summary": "废物少年逆袭…",
  "status": "draft|writing|paused|finished",
  "created_at": "ISO",
  "updated_at": "ISO",
  "chapter_count": 12,
  "db_backend": "sqlite|mysql"
}
```

---

## 2. 模块 1：分作品资料库系统（需求 1、4、10）

基础路径：`/projects/{project_id}`

### 2.1 角色表（Characters）[✅真实]

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/characters` | 新增角色 |
| GET | `/characters` | 列表（支持 `?name=&tag=`） |
| GET | `/characters/{character_id}` | 详情 |
| PUT | `/characters/{character_id}` | 修改 |
| DELETE | `/characters/{character_id}` | 删除 |

**角色 Schema**：`id, name, appearance(外貌), personality(性格), background(身世背景), talent(天赋), experience(过往经历), status(当前状态), skill_ids[](绑定技能ID), faction_id(关联势力), tags[](标签), created_at, updated_at`

### 2.2 技能表（Skills）[✅真实 — 本轮升级，原为占位]

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/projects/{project_id}/skills` | 新增 |
| GET | `/projects/{project_id}/skills` | 列表 |
| GET | `/projects/{project_id}/skills/{skill_id}` | 详情 |
| PUT | `/projects/{project_id}/skills/{skill_id}` | 修改 |
| DELETE | `/projects/{project_id}/skills/{skill_id}` | 删除（级联解除角色绑定） |

**技能 Schema**：`id, project_id, name, level, effect(效果), limitation(使用限制), owner_id(持有者角色ID), side_effect(副作用), unlock_condition(解锁条件)`

> 本轮（§13）另新增**全局写作 SKILL** `/global-skills`，与本表「角色技能」并存但语义不同（前者是 AI 提示词模板）。

### 2.3 关系网表（Relations）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/relations` | 新增关系 |
| GET | `/relations` | 列表（支持 `?character_id=`） |
| PUT | `/relations/{relation_id}` | 修改 |
| DELETE | `/relations/{relation_id}` | 删除 |

**关系 Schema**：`id, subject_id(A), object_id(B), relation_type(友好/敌对/亲人/师徒/上下级/暧昧…), strength(关系强度 0-100), note(特殊恩怨备注)`

### 2.4 势力表（Factions）[✅真实]

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/factions` | 新增 |
| GET | `/factions` | 列表 |
| PUT | `/factions/{faction_id}` | 修改 |
| DELETE | `/factions/{faction_id}` | 删除 |

**势力 Schema**：`id, name, description, leader_id, members[](角色ID), status`

### 2.4b 地点表（Locations）[✅真实]

> 脚手架阶段尚未规划；后续按"坐标系 + 位面"模型补入（见对话演化：点/圆/矩形/扇形/多边形 + plane 分层）。

统一世界坐标系：`x` 向东为正、`y` 向北为正；`plane` 为位面标签（凡间/仙界/地狱/秘境…，即普通文本列）；跨位面坐标不可直接比较，靠"通道"关系连接（待实现）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/locations` | 新增 |
| GET | `/locations` | 列表（返回**纯数组**，非分页） |
| GET | `/locations/{location_id}` | 详情 |
| PUT | `/locations/{location_id}` | 修改 |
| DELETE | `/locations/{location_id}` | 删除 |
| GET | `/locations/{location_id}/geo-relations` | **方位/距离推导**：返回同位面且双方含坐标的其他地点的 `{id, name, bearing(8方位), distance, height_diff}`，跨位面自动排除 |

**地点 Schema**：
```
id, name,
location_type(城市/秘境/洞府/门派/其他),
region(所属区域),
description,
notable_features[](特色地标),
related_ids[](关联角色/势力),
plane(位面，单列文本),
center_x(FLOAT|null), center_y(FLOAT|null),     # 平面坐标
shape(point|circle|rect|sector|polygon),          # 默认 point
radius(FLOAT|null), radius_y(FLOAT|null),         # 圆/扇形半径；矩形半宽 a / 半高 b
angle(FLOAT|null), angle_span(FLOAT|null),        # 扇形中心朝向/张角（度）
height(FLOAT|null),                               # 高度/海拔（第三维）
polygon(JSON|null)                                # 不规则多边形顶点 [[x,y],...]
```

### 2.5 资料库双配置模式

- **手动配置**：前端表单直接调用 §2.1–2.4 的 CRUD 端点；关系图谱由前端可视化编辑后批量 `PUT /relations`。
- **AI 自动配置**：见 §2.7 指令入口，AI 结构化整理后先返回预览（`dry_run=true`），前端弹窗让用户审核，确认后再落库。

### 2.6 设定强制校验（需求 4）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/validate` | 生成前置/后置校验。入参：待校验正文或本次出场实体集合；出参：约束清单 + 问题列表（类型：性格崩坏/技能乱用/关系矛盾；级别：轻微/严重；位置高亮偏移） |

**校验响应示例**：
```json
{
  "code": 0,
  "data": {
    "constraint_list": ["林越-性格:隐忍冷静", "瞬步-限制:每日3次"],
    "issues": [
      {"type":"性格崩坏","level":"严重","offset":120,"length":30,"detail":"林越当众大笑与隐忍冷静冲突"}
    ]
  }
}
```

### 2.7 对话指令自动入库（需求 10）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/command` | 自然语言指令。入参：`{ "text": "添加角色：林越，性格隐忍冷静，孤儿，擅长剑术", "dry_run": false }` |

- 引擎（指令解析引擎）用正则+语义识别提取结构化意图，路由到对应 CRUD；
- `dry_run=true`：返回将执行的变更预览，不落库（AI 自动配置审核用）；
- 返回：执行的变更摘要 + 每条结果状态；无法解析返回 `40002` 并给出澄清问句。

---

## 3. 模块 2/3：章节生成控制器 + 剧情商讨缓存（需求 2、3、6）[✅真实]

> 实现状态：**章节生成（`routers/chapter.py`）与剧情商讨（`routers/discussion.py`）均已真实落地**——章节生成为 **SSE 流式**（`StreamingResponse`，消费默认模型 / Ollama 原生适配器产出正文），商讨对话持久化到 DB（含 `/discussion/chat` 与 `/discussion/global-chat`）。以下端点为真实可用状态；后续扩展方向见 README §8。

### 3.1 剧情商讨会话缓存池（需求 6）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/discussion` | 获取临时商讨缓存（消息列表） |
| POST | `/discussion/messages` | 追加一条商讨消息（闲聊商讨，仅缓存不生成） |
| DELETE | `/discussion` | 清空临时商讨缓存（章节生成完成后归档并清空） |
| POST | `/discussion/archive` | 将当前商讨草稿归档为指定章节备注 |
| POST | `/discussion/chat` | 真实流式商讨回复（SSE，对话级持久化） |
| POST | `/discussion/global-chat` | 未选小说时的全局对话（全局线程 `__global__` 持久化） |

**消息 Schema**：`id, role(user|assistant), content, created_at`

### 3.2 章节生成（需求 2、3）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/chapters/generate` | 触发单章生成（**流式 SSE**） |
| POST | `/chapters` | 非流式保存/落库已生成章节（或批量模式用） |
| GET | `/chapters` | 章节列表 |
| GET | `/chapters/{chapter_id}` | 章节详情（含正文、备注、压缩摘要） |
| PUT | `/chapters/{chapter_id}` | 修改（人工润色后回写） |
| DELETE | `/chapters/{chapter_id}` | 删除 |

**生成请求体**：
```json
{
  "chapter_no": 13,
  "prompt_hint": "林越夜探藏剑阁",
  "from_discussion": true,
  "trigger_foreshadow_ids": ["fs_01"],
  "word_range": {"min":3000,"max":5000},
  "temperature": 0.4
}
```

**硬性生成规则（后端须遵守，已真实落地）**：
1. 单次仅生成单章，字数锁定 3000–5000，输出后自动裁剪/补写；
2. 三层防发散：Prompt 固定模板（禁用套话/排比/万能描写）+ 流式监控截断 + 后置文风过滤词库；
3. 严格遵循用户要求、资料库设定、商讨剧情；不私自加新角色/技能/关系（设定锁死）。

### 3.3 生成流式事件（SSE，见 §0.6）

事件 `event` 类型：`start` / `chunk`（正文片段） / `validate`（校验结果） / `done` / `error`。

```
event: chunk
data: {"text":"夜色如墨，林越贴着墙根…"}

event: validate
data: {"issues":[]}

event: done
data: {"chapter_id":"...","word_count":4180}
```

---

## 4. 模块 4：多厂商统一 API 网关（需求 7）[✅真实]

> 实现状态：模型配置已真实持久化到 `model_configs` 表；真实适配器已落地（见 §4.4）。`/models/test` 会**真实请求厂商接口**验证连通性与延迟；章节生成（`§3`）会消费默认模型产出正文。

### 4.1 端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/models` | 已配置模型列表（**api_key 掩码**为 `***后4位`） |
| GET | `/models/{model_id}` | 模型详情（返回**完整 api_key**，供编辑/测试） |
| POST | `/models` | 新增模型配置 |
| PUT | `/models/{model_id}` | 修改（api_key 传空串表示保留原值） |
| DELETE | `/models/{model_id}` | 删除 |
| POST | `/models/test` | 测试连通性；可带 `model_id` 复用已保存配置，或直接传连接字段 |
| POST | `/models/{model_id}/set-default` | 设为默认生成模型（全局唯一，其余自动取消） |

> 注：原设计的 `/models/{model_id}/invoke` 未单独暴露；生成由章节接口内部经 gateway 调用默认模型。

### 4.2 模型配置 Schema

```json
{
  "id": "uuid",
  "name": "DeepSeek-主创作",
  "vendor": "deepseek|qwen|ernie|spark|kimi|openai|claude|ollama|custom",
  "api_base": "https://api.deepseek.com/v1",
  "api_key": "sk-***（列表掩码；详情返回明文，本地工具未加密存储）",
  "model_name": "deepseek-chat",
  "context_window": 32768,
  "temperature": 0.4,
  "top_p": 0.9,
  "max_tokens": 6000,
  "role": "primary|memory|parse|foreshadow",
  "is_backup": false,
  "status": "active|disabled",
  "is_default": false
}
```

### 4.3 模型分组（role）

`primary`(创作主力) / `memory`(记忆压缩) / `parse`(设定解析) / `foreshadow`(伏笔推演)。用户可自由分配不同任务到不同模型；`is_default=true` 的模型用于「生成章节」。

### 4.4 适配器扩展接口（关键扩展点）

后端 `app/core/gateway/` 下定义抽象基类 `BaseModelAdapter`，已实现 **三个**真实适配器（**仅用标准库 urllib，零第三方依赖**）：

- `adapters/openai_compat.py` — `OpenAICompatibleAdapter`：覆盖 `openai / deepseek / qwen / kimi / ollama / custom / ernie / spark`（OpenAI 兼容 `/chat/completions` 端点；用户需在 `api_base` 指向其兼容地址）。
- `adapters/claude.py` — `ClaudeAdapter`：Anthropic `/v1/messages` 端点（system 顶层 + SSE `content_block_delta`）。
- `adapters/ollama_native.py` — `OllamaNativeAdapter`：Ollama 原生 `/api/chat`，支持 `num_predict` / 动态 `num_ctx`（`_fit_num_ctx`）/ `think` 开关，**章节生成默认走此适配器**。

```python
class BaseModelAdapter:
    vendor: str
    def __init__(self, config: dict): ...            # 含 api_base/api_key/model_name/temperature...
    def chat(self, messages, **params) -> str: ...        # 同步
    def stream(self, messages, **params): ...        # 同步生成器，逐段 yield（章节生成 SSE 用）
    async def astream(self, messages, **params): ...       # 异步包装 stream()
    def test_connection(self) -> bool: ...
```

新增厂商 = 继承该类实现方法 + 在 `adapters/__init__.py` 用 `register(vendor)(Cls)` 注册。**无需改动引擎层代码**。

### 4.5 容错

- 章节生成若**未配置默认模型**，优雅降级为占位文本，保证前端流程不中断。
- 若默认模型调用异常（如密钥无效 401），降级为占位并附错误提示，章节仍落库。
- 文档设计的「同 role 自动切换 is_backup 模型」（42901 限流）**尚未实现**，当前仅使用唯一默认模型。

---

## 5. 模块 5：篇章记忆压缩（需求 8）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/memory/compress` | 对指定章节做结构化压缩（入参 chapter_id） |
| GET | `/memory/summary` | 获取近期有效摘要（最近 3 章详细 + 更早极简大事记） |
| GET | `/memory/events` | 极简大事记列表（更早章节） |

**压缩摘要 Schema**：
```json
{
  "chapter_no": 12,
  "core_event": "林越夺得藏剑令",
  "character_states": [{"id":"c_01","status":"负伤"}],
  "new_foreshadows": ["fs_07"],
  "emotion_shift": "从犹疑到决绝",
  "mainline_progress": "主线30%"
}
```

**拼接逻辑（生成前置 Prompt 组装）**：`近期压缩摘要 + 本章商讨剧情 + 出场角色资料库 + 待触发伏笔清单`。

---

## 6. 模块 6：伏笔线索自动化管理（需求 9）

路径前缀 `/projects/{project_id}/foreshadows`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/` | 手动新增伏笔 |
| GET | `/` | 列表（支持 `?status=pending|active|done`） |
| PUT | `/{foreshadow_id}` | 修改 |
| DELETE | `/{foreshadow_id}` | 删除 |
| POST | `/detect` | AI 根据剧情自动识别新增伏笔（入参章节正文） |
| GET | `/active` | 生成前置检索：返回当前可触发伏笔清单 |
| POST | `/{foreshadow_id}/activate` | 标记伏笔启用回收（记录启用章节，状态→done） |

**伏笔 Schema**：`id, buried_chapter(埋下章节号), description, scene(适用场景), trigger_condition(触发条件), enabled(bool), activated_chapter(启用章节号), related_ids[](关联角色/势力), status(pending|active|done)`

---

## 7. 模块 7：剧情走向推荐（需求 5）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/chapters/{chapter_id}/directions` | 单章生成后推演后续走向（入参：结尾剧情等，由后端自动读取） |
| GET | `/chapters/{chapter_id}/directions` | 获取已推演的走向列表 |
| POST | `/directions/{direction_id}/select` | 用户选中某走向 → 自动加入下一轮商讨缓存 |

**走向 Schema**：
```json
{
  "id": "uuid",
  "core_conflict": "正邪两道围堵藏剑阁",
  "applicable_foreshadows": ["fs_03"],
  "character_change": "苏晚黑化",
  "style_bias": "紧张悬疑",
  "confidence": 0.82
}
```

输出 3–5 条差异化走向；推演温度 `0.7`。

---

## 8. 模块 8：小说套路模板组件（需求 11）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/templates` | 模板库列表（秘境夺宝/宗门大比/穿越重生/复仇逆袭/悬疑探案/团战突围/都市奇遇…） |
| POST | `/templates/{template_id}/outline` | 基于模板+历史摘要生成大纲（入参：参与角色/对立势力/核心矛盾/背景来源） |
| GET | `/outlines` | 大纲列表 |
| POST | `/outlines` | 保存大纲 |
| PUT | `/outlines/{outline_id}` | 修改大纲（章节增删改） |
| DELETE | `/outlines/{outline_id}` | 删除 |

**模板配置入参**：
```json
{
  "template_id": "tmpl_revenge",
  "participants": ["c_01","c_02"],
  "opponent_faction": "f_03",
  "core_conflict": "灭门之仇",
  "background_source": "manual|ai_auto",
  "background_text": "...",
  "config": {"conflict_node":"…","mid_turn":"…","ending":"…","est_chapters":30}
}
```

**两种生成模式**：①逐章生成（调 §3.2 单章）；②批量预生成（一次性多章草稿，落库待审）。

---

## 9. 温度/约束统一参数（底层约束）

| 任务 | temperature | 说明 |
| --- | --- | --- |
| 剧情章节生成 | 0.3–0.5 | 低发散 |
| 创意走向推演 | 0.7 | 高创意 |
| 记忆压缩 | 0.2 | 稳定抽取 |
| 设定解析 | 0.3 | 结构化 |
| 伏笔推演 | 0.5 | 中等 |

**全局硬约束**（任何模型调用前由控制器注入）：
- 设定锁死：未经用户指令新增的实体，AI 禁止私自添加；
- 上下文上限：固定窗口，摘要严格控长；
- 日志留存：章节、资料库修改、伏笔记录永久持久化（写操作统一落审计日志表）。

---

## 10. 可拓展性设计（扩展指南）

### 10.1 新增一个业务模块

1. 后端：在 `backend/app/routers/` 新建 `xxx.py`，用 `APIRouter` 定义端点，在 `main.py` 注册 `app.include_router(xxx, prefix="/api/v1")`，Schema 放 `schemas/`，业务桩放 `services/`；
2. 前端：在 `frontend/src/api/` 新建 `xxx.js` 调用桩，`frontend/src/views/` 新建页面桩，`frontend/src/router/index.js` 追加路由；
3. 文档：在本文件追加对应 § 章节，并在 [`../docs/接口与组件文档.md`](../docs/接口与组件文档.md) 留一份组件清单。

### 10.2 新增一个模型厂商

仅实现 `BaseModelAdapter` 子类并在 `gateway/registry.py` 注册 `vendor` 字符串，引擎层零改动（见 §4.4）。

### 10.3 前端组件解耦

- 所有后端调用集中在 `src/api/*`，视图层不直接写 URL；
- 页面桩通过 `props`/`emits` 暴露交互边界，便于后续注入真实逻辑；
- 关系图谱、伏笔时间轴等可视化组件独立成 `components/`，接收标准 Schema 数据。

---

## 11. 参考文档（需求 8，按 project 隔离）[✅真实]

每本小说可手动上传参考素材（大纲、设定笔记、同人资料、背景资料等），AI 生成章节时会自动读取。

> 这里叫「参考文档」（参考图 1 的「参考资料」按钮指向同一组端点）。

### 11.1 端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/projects/{project_id}/references` | 上传参考文档（filename / content_text） |
| GET | `/projects/{project_id}/references` | 列表（不含正文，仅摘要） |
| GET | `/projects/{project_id}/references/{doc_id}` | 详情（含正文） |
| DELETE | `/projects/{project_id}/references/{doc_id}` | 删除 |

支持格式：`.txt / .md / .json / .csv / .log` 等文本。PDF / Word 等二进制解析后续扩展。单文档正文硬上限 200K 字符。

---

## 12. 全局设定库（需求 12，跨小说复用）[✅真实]

> 全局共享：与作品无关，多本小说可复用同一套设定（创建小说时让用户挑选）。
> 类别约定：`境界 / 货币 / 体系 / 规则 / 其它`。

### 12.1 端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/settings` | 列表（支持 `?category=&keyword=&template_only=`） |
| POST | `/settings` | 新建 |
| GET | `/settings/{setting_id}` | 详情 |
| PUT | `/settings/{setting_id}` | 修改（全字段可空） |
| DELETE | `/settings/{setting_id}` | 删除 |

### 12.2 Schema

```json
{
  "id": "uuid", "name": "玄幻九境界", "category": "境界",
  "levels": ["炼气","筑基","金丹",...],
  "description": "...", "tags": ["玄幻","高武"],
  "is_template": true,
  "created_at": "ISO", "updated_at": "ISO"
}
```

### 12.3 生成时拼接

与 §11 类似：章节生成（§3.2）触发时，`{project_id}` 命中的设定若标 `is_template=true`，将 `levels + description` 序列化为文本片段拼入 Prompt。

> 可扩展点：`settings.teach_cache_by_template(project_id)` —— 缓存高频模板减少 IO（TODO）。

---

## 13. 全局写作 SKILL（需求 13，跨小说复用）[✅真实]

> 全局共享：与作品无关。**与资料库的 Skill（§2.2）语义不同**：本节 SKILL 是「AI 提示词模板」，按 `trigger`（discussion / chapter / memory / parse / all）注入对应阶段 Prompt。

### 13.1 端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/global-skills` | 列表（支持 `?trigger=&enabled_only=&keyword=`） |
| POST | `/global-skills` | 新建 |
| GET | `/global-skills/{skill_id}` | 详情 |
| PUT | `/global-skills/{skill_id}` | 修改 |
| DELETE | `/global-skills/{skill_id}` | 删除 |

### 13.2 Schema

```json
{
  "id": "uuid", "name": "古风用词器",
  "description": "生成时优先用四字成语替代口语",
  "prompt_body": "...（注入到 AI 提示词的完整正文）",
  "trigger": "chapter",     // discussion | chapter | memory | parse | all
  "enabled": true,
  "tags": ["古风"],
  "created_at": "ISO", "updated_at": "ISO"
}
```

### 13.3 调用约定

- `trigger=chapter` 在 §3.2 章节生成时按需注入；
- `trigger=all` 在所有阶段都注入；
- 多个 SKILL 命中同一 trigger 时，按 `name` 字典序拼接（避免顺序漂移导致缓存无效）。

> 调度已实现：`priority` 字段（数值大者先生效，互斥类仅留 priority 最高者）；`cooldown` 为后续可扩展点（防注入过度）。

---

## 14. 工作流（需求 14，跨小说复用）[✅真实]

> 全局共享：可重用的剧情 / 创作流程模板（DAG：节点 + 条件边）。
> 本轮仅做 CRUD + JSON 编辑；可视化拖拽（vue-flow 接入）后续扩展。

### 14.1 端点

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/workflows` | 列表（`?active_only=&keyword=`） |
| POST | `/workflows` | 新建（节点 / 边 JSON 自动校验 DAG 端点） |
| GET | `/workflows/{wf_id}` | 详情 |
| PUT | `/workflows/{wf_id}` | 修改 |
| DELETE | `/workflows/{wf_id}` | 删除 |
| POST | `/workflows/{wf_id}/duplicate` | 复制（id 重生，name 加「(副本)」） |

### 14.2 Schema

```json
{
  "id": "uuid", "name": "开篇套路",
  "description": "钩子 → 冲突引入 → 第一波冲突",
  "nodes": [
    {"id":"start","type":"start","label":"开篇", "params":{}, "position":{"x":0,"y":0}},
    {"id":"hook","type":"step",  "label":"钩子"}
  ],
  "edges": [
    {"from":"start","to":"hook","condition":"always"}
  ],
  "tags": ["开篇"],
  "is_active": true,
  "created_at": "ISO", "updated_at": "ISO"
}
```

`FlowEdge.condition ∈ {always, onSuccess, onFailure}`，自定义字符串也允许（向后兼容）。

### 14.3 运行时（TODO）

后续接「工作流执行」时，根据 `edges.condition` 调度 §4 模型网关：

```
工作流开始 → 调用 gateway 串行/分支执行 node × params → 收集产物 → 触发依赖节点
```

> 可扩展点：
> - `version` 字段：工作流派生版本管理
> - `execution_history`：运行时记录（按章节关联）
> - DAG 编辑器：vue-flow 双向绑定

---

## 15. 待定 / 后续补全（非脚手架阻断项）

- 鉴权与多租户（§0.3）；
- 文件/图片类资源上传（封面、关系图谱导出）；
- WebSocket 与 SSE 二选一的正式确定（当前默认 SSE）；
- 限流策略具体参数（QPS、并发）；
- 审计日志表结构细化；
- 工作流执行引擎（§14.3 TODO）；
- SKILL `priority / cooldown`（§13.3 扩展点）。

> 本文档随开发推进持续修订，版本号递增。任何偏离本规范的设计须先更新本文档再编码。
