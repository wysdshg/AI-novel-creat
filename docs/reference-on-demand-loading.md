# 参考文件「按需加载」机制设计文档

> 适用：AI 小说创作智能体后端。`E:\AI小说创作\backend`
> 接口范围：商讨对话（`/discussion/chat`，phase 1）/ 章节生成（phase 2，待接）
> 最后更新：2026-08-09

## 1. 背景与目标

参考资料（取名素材、设定库导出、世界地图笔记等）会随项目增长而膨胀。若每次推理都把**全部**参考塞进 Prompt，会：

- 占用大量上下文窗口，挤压正文生成空间；
- 线性放大 token 成本（文档越多越贵）。

设计目标：**让 AI 自己决定要读哪些文件**，只把选中文件的正文注入上下文，避免无用文件占窗、也避免多轮请求反复重传前缀。

核心结论（实测）：用 `prompt 缓存（前缀 KV 复用）+ 工具调用式批量加载（一次往返取回全部选中文件）+ 复用现有相关性预排`，净 token 是**降**的，不是升的。

## 2. 两阶段协议

```
前端/调用方
   │  POST /discussion/chat（含 messages）
   ▼
[后端] 组装 system：
   - 基础设定 + SKILL 注入
   - ★ 目录前缀：format_catalog_prompt() 渲染「可用参考文件清单」（稳定，可缓存）
   ▼
Pass1：adapter.chat(messages, think=false)  ← 非流式，拿模型首轮文本
   │
   ▼  ref_selector.select(first_text)  →  selected_ids
   │        ├─ None        ：模型判断无需参考 → 首轮文本即最终回答（仅 1 次调用，省）
   │        └─ [id,…]      ：需要参考
   ▼
fetch_refs_by_ids(db, ids)  ← 一次往返批量取正文（不是一文件一请求）
   │
   ▼ 把正文作为一条 user 消息追加（"已按你的请求加载以下参考资料…"）
   │
Pass2：adapter.stream(messages)  ← 带思考，流式输出最终回答
```

- **懒加载**：只有「需要参考」的任务才走 Pass1；闲聊直接走旧单次流式。
- **批量取回**：无论选中 2 个还是 20 个文件，`fetch_refs_by_ids` 永远 **1 次 DB 往返**，不是 N 次。
- **选中内容留历史**：注入后留在 messages，后续轮次免重取；配合前缀缓存摊薄成本。

## 3. 选择阶段策略层（本次抽象对象）

`Pass1 → selected_ids` 这一步被抽象为策略，文件：`backend/app/services/reference_selector.py`。

### 策略 A — `MarkerSelection`（现状默认，实装）

- 解析约定文本标记：`LOAD_REFS:<id1>,<id2>`。
- 实现：`reference_crud.parse_load_refs`（正则 + 容错，已验证 5 用例）。
- 适用：**任何能吐文字的模型**（本地 4b / OpenAI / Claude 通用）。
- 选择原因：本地 `qwen3.5:4b` 对原生 `tool_calls` 结构化解析不稳，但输出约定文本可靠、可实测。

### 策略 B — `ToolCallSelection`（占位，未启用）

- 目标：解析强 API 的原生 `tool_calls`（`retrieve_refs(ids=[...])` 工具）。
- 现状：`select()` 抛 `NotImplementedError`，未接入主链路。
- 未来实现要点（见文件 docstring）：
  1. 适配器 `chat()` 需暴露 `tool_calls`（当前只返回纯文本 str，需扩展）。
  2. 定义工具 schema：`retrieve_refs(ids: list[str])`。
  3. 从 `raw` 取 `tool_calls[].function`（name == "retrieve_refs" → arguments.ids）→ `fetch_refs_by_ids` 校验。
  4. 工具结果作为 tool 消息回灌 → 续答（即现有 Pass2）。
- **关键**：无论 A 还是 B，`selected_ids` 之后的 `fetch/inject/Pass2` **完全共用**，切换是「插拔」，不动主链路。

### 取策略的方式

```python
from app.services.reference_selector import get_reference_selector
ref_selector = get_reference_selector()
# 优先级：参数 mode > 环境变量 NA_REF_SELECTOR > 默认 "marker"(A)
```

- 默认 `marker`（A），保证现状行为不变。
- 未来切强 API：设 `NA_REF_SELECTOR=toolcall` 并实现 B 即可，router 代码零改动。

## 4. 目录数据来源（catalog）

端点：`GET /projects/{pid}/references/catalog`、`GET /references/global/catalog`
（均挂 `/api/v1`，范围含全局池 `include_global=true`）

字段来自 `ReferenceDocORM`（已存列，仅列表 schema 之前漏暴露），`ReferenceCatalogItem` 补充：

| 字段 | 来源 |
|---|---|
| id / filename / summary / tags / source / size | ORM 已有列 |
| content_chars | `len(content_text)` 运行时算 |
| token_est | `round(content_chars / 1.5)`，与 `budget.py` 口径一致（中文 1 token≈1.5 字符） |
| locked | `source=='auto' or article_id 非空` → AI 不可跳过，永远预置 |

`build_catalog` 复用 `pick_relevant` 的相关性打分做预排，locked 置顶。

## 5. 文件清单

| 文件 | 改动 |
|---|---|
| `services/reference_selector.py` | **新增**：选择策略层（A 实装 / B 占位 / 工厂） |
| `services/reference_crud.py` | `estimate_tokens` / `build_catalog` / `format_catalog_prompt` / `parse_load_refs` / `fetch_refs_by_ids` |
| `schemas/reference.py` | 新增 `ReferenceCatalogItem` |
| `routers/references.py` | `GET .../references/catalog` |
| `routers/reference_global.py` | `GET /references/global/catalog` |
| `core/gateway/adapters/ollama_native.py` | `_stream`/`chat` payload 加顶层 `cache_prompt: True`（前缀缓存前提） |
| `routers/discussion.py` | 目录前缀注入 + 两阶段 + `ref_selector.select()` 接线 |

## 6. 实测验证（探针，已清理）

1. `build_catalog` 返回全局池 7 条，`token_est/summary/tags/locked` 正确；
2. `parse_load_refs` 5 用例全过（夹带文字 / 空串 / `LOAD_REFS:` 无 id 等容错）；
3. 真实两阶段：问「古言温婉女主取名」→ 模型输出 `LOAD_REFS:8ab305…,d0fbcf…`（女尾字100 + 女性小说名300）→ 后端精准加载这 2 份 → Pass2 基于参考给出名字建议。机制端到端跑通。

## 7. 已知缺口 / 下一步

- [ ] **phase 2**：把同一机制接入章节生成（`builder.py` 当前走 `pick_relevant` 全量注入），直接省生成 token。
- [ ] **策略 B 实现**：切强 API 时落地 `ToolCallSelection`（见 §3）。
- [ ] **前缀缓存验证**：`cache_prompt: True` 已加，但需在真实多轮对话中用 Ollama 缓存命中率确认收益。
- [ ] **全局池在线拉取 UX**：目录下含全局池，前端可加「一键导入本作品」按钮（复用 `import_global_references`）。

> ⚠️ 后端改代码须手动重启（`E:\` 共享盘 uvicorn reload 不生效）：宿主运行 `.venv\Scripts\python.exe backend/dev.py` 重启后生效。
