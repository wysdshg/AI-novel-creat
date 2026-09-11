# 变更记录

> **每次改动必须记一行。** 格式：`日期 · 改动摘要（影响范围）`
> 立此文件的原因：git 历史 16 次提交里 11 次是 `fix:`，回归率约 70%——缺的就是"改了什么"的可追溯记录。

---

## 2026-09-11
- **Phase 7.1 试点跑通：修真四万年前 30 章 · 硅基流动 Qwen/Qwen3-8B**：
  - 新增 `services/plot_import.py`：小说目录 → 逐章概括（幂等断点续跑）→ 情节段切分 → 段分类。**直连硅基流动不走 gateway**（`enable_thinking=false`，Qwen3 思考会吃光输出预算并拖慢 60s+）；**串行 2s 间隔 + 429/5xx 指数退避**（防限流封禁）；key 复用 `retrieval.siliconflow_key`。
  - **试点结果**：30 章概括 0 失败；19 段 + 19 标签；总耗时 29 分钟。章概括质量高（人物/地点/物品/数字全齐）。
  - **暴露三个真问题（记录在案）**：段切太碎（1.6 章/段）；标签噪声（6 段同标"追逃猎杀"）；跨批次段切断。修复方向已写入 docs/03 Phase 7.1。
  - 速度注记：~34s/章 → 755 章全量约 7 小时，放量前需并发优化（3~5 并发 + 令牌桶）。
  - 单测 11 用例（mock LLM 全覆盖：幂等续跑 / 失败补跑 / 漏标兜底 / 坏 JSON 回退 / 重算清旧段）。
- **Phase 7 立项：模板库与规划驱动写作（用户拍板，docs/03）**：
  - **背景**：用户对现状的核心批评 —— 当前生成链路只服务「已写完全书大纲」的作者，输入侧（规划）是空的；卡文/水情节根因是缺「章计划」中间层（一篇概括几百字直接扩几万字必然发散）。
  - **拍板三项**：① 入库「人工合并」= AI 给候选组 + 用户点确认；② 起步 20 本，但先 Qwen3-8B（Ollama 零成本）跑 1~2 本验证概括质量；③ 章计划用新表（不复活 outlines）。
  - **四子项**：7.1 模板库（`plot_templates` + `chapter_summaries`，结构 = phase→beat→variants，**chunk 粒度 = beat**，向量化进 vector_chunks 复用 A 线检索）；7.2 篇规划流（`article_plans` 新表 + 行级 refine + 三种"未找到"降级 + `layer_chapter_plan` 生成联动）；7.3 批量生成器（连写 M≤3 + 同步摄取 + 断点恢复）；7.4 FC 闭环（`retrieve_templates` 单工具、仅规划会话、可降级嵌入式）。
  - **价格事实（同日核实）**：DeepSeek V4.1 Flash 缓存命中 0.02 元/M（1/50 折扣）→ 闭环最坏 5 步 ≈0.025 元与现状持平，经济不是约束；Qwen3.8-Flash-Next verbose（输出 2×）+ TTFT 方差为交互短板。
  - §3 销掉两条待拍板：套路模板形态、篇层必要性（**篇 = 规划单元**）。
  - 实施顺序 7.1→7.2→7.3→7.4；MVP 门槛：20 本灌完后混合口述能召回正确模板族。

## 2026-09-10
- **README 正式化拆分（深夜，9624dae）**：README.md 面向 GitHub 访客重写（项目简介/功能四组/架构/从零搭建快速开始/路线图）；AI 向内容拆至 AIREADME.md（AI 助手任务入口：权威文档表 + docs/06 指引 + 工作环境事实 + 密钥红线）。
- **Phase 4.2 + 4.3 观测消费端（token 计量 / trace_id 贯通 / 章节改动回流）**：
  - **4.2 要解决的问题**：`trace_id` 只在响应信封、从不落库；token 用量完全没提取 ——「这个月花了多少 token / 哪个场景最费 / 换模型后成本涨了多少」无法回答。
  - **适配器提取 usage（零签名侵入）**：用 `adapter.last_usage` 属性传出（流式是生成器无法 return，改签名会波及所有调用方）。三家字段归一：OpenAI `prompt_tokens`；**Claude 分散在 `message_start` + `message_delta` 两个事件、必须累积**（只取一处丢一半）；Ollama 只在 done 帧。
  - **如实区分真实/估算**：多数厂商流式不回 usage → 按字符估算标 `estimated=True`；`normalize_usage` 取不到返回 **None 不硬造 0**（否则"没数据"伪装成"零消耗"）。失败调用也记（`ok=False`，prompt 已发出同样烧钱）。
  - **trace_id 贯通**：生成时生成 12 位 id → 用量记录 + 日志 + `done` 事件三处同步，三者可互相对上。
  - **顺带修一处健壮性**：OpenAI 流式**末帧常带 usage 且 `choices` 为空数组**，原代码 `obj["choices"][0]` 会 IndexError、被当成"畸形帧"记 warning → 改为先取 usage、再安全取 choices。
  - **4.3 要解决的问题**：「作者改了正文」这一**最强改进信号**完全丢弃，模型下次照犯。由 `PUT /chapters/{id}` **自动捕获**（无需前端上报）：对比该章**最新 AI 版本**（Phase 4.1 的留档正好复用）与提交正文，`difflib` 算相似度与改动统计。只记统计特征 + 200 字样本（不存全文，避免与 `chapters.content` 不一致）；相似度 ≥0.999 不记（点了保存不算反馈，防噪音）。`feedback_records` 表 + 列表/stats 接口 —— **`avg_change_ratio` 最该盯：长期偏高 = AI 稿子离"能用"差得远**。
  - **重要发现并补上**：前端**没有正文查看/编辑入口**（ChapterListView 只能改标题、ChatView 无正文面板）—— 没有编辑入口，反馈就无从产生 → 补章节列表**「正文」抽屉**（查看 + 编辑 + 保存 + 已修改提示）。
  - **验证**：`test_observability.py` **29 用例**；全量 **208 全绿**；真机端到端 **19/20**（唯一失败是我验证脚本把建篇路径写错成 `/projects/{pid}/articles` → 405，真实路径是 `/projects/{pid}/volumes/{vid}/articles`，**非产品问题**）：改正文自动生成反馈（改动幅度 **0.407** / 相似度 **0.593** / 长度 240→165）、无改动不记、stats 聚合正确、清理干净（作品/反馈/用量全归零）。
  - **接口**：5 个新端点，路由 144→**149**、paths 85→**89**。**前端**：左侧栏**「观测」**页（用量 + 反馈两 tab，`ObservabilityView.vue` + `api/observability.js`）。
  - **边界（如实记录）**：用量**只覆盖章节生成**（商讨/写后摄取/指令解析未计量，统计会偏低）；走向采纳/拒绝未做；金额换算未做（token 已计量）。
- **Phase 4.1 最小 eval（生成版本留档 + 人工打分 + 对比）**：
  - **要解决的问题**：此前**没有任何工具**能回答「我改了配置（换模型 / 调温度 / 开检索），生成的章节是变好了还是变坏了」—— 只能凭感觉。这是 Phase 4「Agent 闭环」的第一环。
  - **① 自动留档**：每次生成/重新生成章节，`chapter.py` 保存段自动把本次生成存为一个**版本**（新表 `chapter_variants`）＝ **配置快照**（vendor / model_name / 温度 / max_tokens / ref_mode / 摄取档位 / 字数目标 / 思考开关）+ **正文快照** + **自动指标**（耗时、字数、去AI味得分、是否复读中断、错误备注、上下文摘要）。**用户零额外操作**。
  - **② 人工打分**：`POST /variants/{vid}/eval`，1~5 总分 + 备注（新表 `eval_records`）。**追加式** —— 同版本可重复打分、保留历史，便于回看自己的标准有没有漂移。
  - **③ 对比**：`.../variants/compare` 给均分与最高分及其配置；页面把各版本的配置与指标并列。
  - **四个关键取舍**：
    1. **正文整存**，不引用 `chapters.content` —— 重新生成会覆盖原章，而"能看见旧版本"恰恰是评估的前提（单测锁定：改了原章不影响已留档版本）。
    2. **指标放 JSON**（`config_snapshot` / `metrics`）—— 指标会持续增加，不值得每加一个就改表。
    3. **旁路设计** —— 留档整段包 try，任何异常只少一条记录、**绝不冒泡到生成主链路**（单测：db 损坏时返回 None 不抛）。
    4. **级联** —— 删章连带清版本与评分，否则留下带正文的孤儿版本污染对比列表（单测锁定"只删该章、不误伤别的章"）。
  - **验证**：`tests/unit/test_eval.py` **19 用例**（含分数越界拒绝、`True/False` 显式挡掉、重复打分取最新、对比选最高分、级联作用域）；全量 **179 单测全绿**；真机 8012 —— 5 个新路由可达（**不是 404**）、空数据返回结构正确、`init_db` 自动建两张新表、**日志落盘同时验证生效**。
  - **接口**：5 个新端点，路由 139→**144**，openapi paths 81→**85**。
  - **前端**：左侧栏新增**「生成评估」**入口（`views/EvalView.vue` + `api/eval.js`）。⚠️ 特意确认入口存在 —— 本项目已两次出现"代码完整、路由存在、但用户点不到"（见 06 手册「零入口」）。
  - **仍未做（Phase 4 余下）**：4.2 `trace_id` 落库 + token 计量；4.3 "用户改了正文"这一最强反馈信号回流；4.1 目前只覆盖章节、对话回复未纳入。
- **文档校正 + function calling 规划**：
  - **校正过时内容**：`docs/01` §7 十二环差距表有两条已被追上 ——「工程基建 ❌ 零测试/零 logging」→ **160 单测 + 日志落盘**；「知识/检索 🟡 待优化」→ **A 线已实施并验收**。同时校正 §2 进度表（库里作品已为 0，附备份可恢复说明）、§5.1 检索（待优化 → 已完成）、§5 不做清单；`docs/02` §6 数据快照整节重写；路由口径统一为 **81 条路径 / 139 个路由条目**（原写 82/83 混用）。
  - **新增 function calling 规划**：`docs/03` **Phase 6**（核心判断：项目不缺工具调用、缺**闭环**；4 种手搓替代品的硬伤；P0~P3 优先级；工程配套 7 条；**前提条件取决于主力模型**；3 步推进顺序）；`docs/05` **§11**（现有 4 种交互模式 + `reference_selector.py` 的 A/B 策略抽象层）；`docs/06` 强制检查区加"动工具调用前先读什么"的指引；`docs/01` §7 工具调用条目指向 Phase 6。
- **后端日志落盘 + 崩溃取证（让「运行着运行着就挂了」可追溯）**：
  - **背景**：后端反复「运行着运行着就挂了」，事后**完全无法追溯**——原先日志只输出到控制台，终端窗口一关证据就没了；项目里那几个 `.log` 全是 8 月的旧文件。本次彻查该问题时，连"是崩溃还是被杀"都判断不了，只能靠排除法。故补上落盘。
  - **落盘**：`backend/logs/backend.log`（INFO+，5MB×5 轮转）+ `error.log`（WARNING+，2MB×3），UTF-8。**启动方式完全不用改**——只要走 `main.py`（`python dev.py` / `uvicorn main:app` 都一样）自动生效。
  - **取证四件套**（核心价值）：
    1. **启动/退出标记** —— ★「有启动、无退出」即说明被**强杀**或硬崩溃（`taskkill /F` 不触发 `atexit`）；成对出现则是优雅退出。**这一条直接回答"是不是被杀"**。
    2. **未捕获异常钩子**（`sys.excepthook` + `threading.excepthook`）—— 落 CRITICAL + **完整 traceback**。后台线程尤其重要：本项目写后摄取/工作流/SSE 都是线程，这类异常默认只印到 stderr，窗口一关就查无此案。
    3. **心跳**（默认 5 分钟，含 `RSS=` 内存与线程数）—— 最后一条心跳即**进程确切死亡时间**；内存持续上涨可确诊泄漏（"越跑越卡最后挂掉"多半是这类）。可用 `NA_HEARTBEAT_SEC` 调整。
    4. **uvicorn 三个 logger 单独挂 handler** —— 它们 `propagate=False` 不走 root，否则「哪个请求把它打挂了」的线索全丢。
  - **踩坑**：`uvicorn.error` 默认 `propagate=True` 会流到父 logger `uvicorn`，两者都挂 handler 会让**同一条日志写两遍**（实测发现）→ 改为动态判断"是否会被祖先 handler 覆盖"，是则跳过。
  - **踩坑**：新写的 `logging_config.py` 里有 9 处静默 `except`，**被 Phase 3.5 自己写的护栏测试当场抓住**。正确处理不是降低标准，而是**显式豁免日志基础设施**——它的 except 分支不能调 logging（handler 未建好会二次失败、异常 hook 里会递归、退出阶段 handler 可能已 shutdown），豁免登记在 `_EXEMPT_FILES` 并写明理由。
  - **验证 12 项**：优雅退出有标记 ✓ / **强杀无标记** ✓ / 主线程异常落 traceback ✓ / 后台线程异常落 traceback ✓ / **5 条 uvicorn.access 请求日志落盘** ✓ / 心跳 ✓ / 中文未转义 ✓ / `error.log` 分级正确 ✓ / 日志不重复 ✓。**160 单测全绿**。
  - **环境变量**：`NA_LOG_DIR`（目录）、`NA_LOG_FILE`（主文件名）、`NA_LOG_LEVEL`、`NA_HEARTBEAT_SEC`。判读方法见 `docs/05-架构与接口.md` §9.2.1。
- **Phase 3.5 全量 `except Exception` 补齐日志（107 处，消除 53 处「静默吞异常」）**：
  - 用 `ast` 静态扫描 `backend/app/**/*.py`，把 broad-except 分成「已记日志 / 已 re-raise / **吞掉且既无日志也无 raise**」三类。实测 **107 处 broad-except，其中静默 53 处**（原计划估 78 处，实际更多；涉及 23 个文件，其中 10 个连 logger 都没有）。这类站点最要命：功能不工作时**服务端零痕迹**，只能靠用户描述来猜。
  - **按类型分四类处置（不搞一刀切）**：
    1. **`pass` / `continue` 完全静默型**（19 处）→ 全部补 `logger.warning` 并带可定位上下文。典型：SSE 单帧解析失败原本 `continue`，现在记 `跳过无法解析的 SSE 帧: <异常>; data=<原始片段>` —— 若某厂商改了响应结构，这条会连续刷，是唯一线索。
    2. **`return False/None/空` 降级型**（7 处）→ 补 warning，写清"降级成了什么"（如「vec_index 探测失败，回退 Brute 实现」），否则「为什么一直在用慢实现」毫无线索。
    3. **已把错误回给用户的**（8 处：`fail()` / SSE 文案 / `NodeResult(status='failed')`）→ 补 `logger.exception`。**理由：前端只显示 200 字截断文案，堆栈只有日志里有**；后台线程（工作流执行）的异常更是只能靠日志。
    4. **重复触发型**（如 sqlite-vec 扩展**每个新连接**都加载一次）→ 用 `logger.debug`，避免 warning 刷屏；排查时 `NA_LOG_LEVEL=DEBUG` 可见。
  - **顺带修 1 个会误导排查方向的文案**：`model_crud.test_connection` 在 status=-1（**根本没拿到 HTTP 响应**：DNS 失败 / 连接被重置 / 超时）时也显示「连接失败（厂商返回非 200）」→ 改为「（无法连通或厂商返回非 200）」。
  - **新增护栏测试** `backend/tests/unit/test_except_logging.py`（2 例）：① 禁止 `app/**/*.py` 出现「无日志、无 raise、无 `noqa` 豁免」的 broad-except；② **哨兵测试**——断言扫描到的 broad-except ≥80 处，防止「因扫描逻辑失效而扫不到 → 测试假绿」。**护栏有效性已实证**：故意注入一处 `except Exception: pass` → 立即变红并精确报出 `load_observation.py:68`，随后还原。
  - **验证**：全量 **160 单测 passed**（158 + 2 新护栏）；139 路由不变；真机 8011（**用户 8000 全程未动**）**12/12** —— 含**真实触发网络异常**以证实新增日志真的会打出：日志出现 `WARNING [app.core.gateway.adapters.openai_compat] [openai_compat] HTTP 请求异常 url=http://…/chat/completions: ConnectionResetError: [WinError 10054] …`；同时全程**仅 1 条 WARNING、0 ERROR**（确认无日志噪声回归）；全局对话 SSE 仍为 `context → chunk → done`、中文未被转义。验证完临时实例与数据即清理。
- **Phase 3.4 统一 SSE 帧编码 + 模型解析（消 3 份 + 15 处重复，修 1 个真 bug）**：
  - **① SSE 帧编码 → `backend/app/core/response.py::sse_event(event, payload)`**：`chapter.py` / `discussion.py` / `workflow.py` **各写一份逐字相同的 `_sse()`**，另有 **15 处手拼裸帧**（`f"event: chunk\ndata: {json.dumps(...)}\n\n"`、`yield "event: done\ndata: {}\n\n"` 之类），全部收敛到单一实现。函数内部保证两条契约：
    - **`ensure_ascii=False` 不能漏** —— 否则中文正文全变 `\uXXXX` 转义（体积翻倍、前端还要再解一轮）；
    - **帧尾必须是空行 `\n\n`** —— 前端按 `split('\n\n')` 切帧，缺空行会把相邻两帧**粘成一帧**（表现为"事件丢了/乱码"）。
    - **新增护栏测试** `test_sse_stream.py::test_no_raw_sse_frames_left_in_routers`：扫 `app/routers/*.py` 禁止再出现裸帧字面量。**首次运行即失败**，抓出 4 处人工搜索漏掉的 `yield "event: done\ndata: {}\n\n"`（`discussion.py` 三个 `done` 分支）—— 这正是自动化护栏相对于"我搜过了"的价值。
  - **② 模型解析 → `backend/app/services/model_crud.py::resolve_model(db, model_id)`**：原先 `chapter.py` / `discussion.py::_resolve_model` / `assist.py` / `config_command.py` **四份各自实现、细节已漂移**。统一语义：**显式 `model_id` 且 `status=='active'` 才用它，否则回退默认模型；默认模型本身非 active 或库里无可用模型 → 返回 `None`**（调用方须 `fail(...)` 提示用户去「模型配置」添加并设为默认）。
    - **修出一个真 bug**：`chapter.py` 原先写 `db.query(ModelConfigORM).filter_by(id=body.model_id).first()`，**完全绕过 active 校验** —— 已被停用/删除的模型只要 id 还在库里就照样被拿去发请求（轻则 401/404，重则打错模型）。`discussion.py` 两处 `use_model = default is not None and (default.status or "active") == "active"` 又与 `assist.py` 不一致。现 4 处行为完全一致。
  - **新增 `backend/tests/unit/test_model_resolve.py` 14 例**：显式 active 优先 / **显式 inactive 回退默认（核心回归）** / 未知 id 回退 / 无 id 取默认 / 无默认回退首个 active primary / 默认 inactive 返回 `None` / 空库返回 `None`；外加一个用 `ast` 解析源码（**剥掉 docstring 与注释**，避免匹配到解释性文字）的**调用方护栏测试**，禁止任何模块再手搓模型解析。
  - **踩坑**：`ModelConfigORM` 字段名是 **`vendor` 不是 `provider`**；且 `vendor` / `role` 都是 Pydantic `Literal` 约束 —— `"openai_compat"`（那是适配器名）与 `"secondary"`（非法角色）都会直接抛校验错，测试里改用 `"custom"` / `"parse"`。
  - **验证**：全量 **158 单测 passed**（144 + 14；`test_sse_stream.py` 因 `_sse` 迁移改了 import 并 +2 例）；后端可加载、**139 路由**不变（139 = 134 条 `/api/v1` 业务路由 + 5 条框架路由）；真机 8010（**用户 8000 全程未动**）**10/10 通过** —— workflow 与 discussion 两类 SSE 流逐帧断言 `ensure_ascii=False` 生效（中文未被转义）与 `\n\n` 切帧正常，**并确认终帧 workflow = `run_end` / discussion = `done`**（顺带修正 05 文档把 workflow 终帧误写成 `done` 的错误）。验证用的临时工作流 3 个、临时作品 1 个已删净，用户真实数据未动。
- **Phase 3.3 抽公共 SSE 工具 + SVG 视口 composable（消 4 份 + 2 份重复，顺带修 2 个真 bug）**：
  - **`frontend/src/utils/sse.js`（新）**：抽出 `createSseParser`（纯解析器，可单测）/ `readSseStream`（**HTTP 状态校验 → 读流 → 超时/外部中止 + `GenerationStopped` 语义**）/ `createTimeoutController` / `postSseStream`（一站式 POST+读流）。改造前 `chapter.js` / `discussion.js`（2 处）/ `workflow.js` **各自手写**「`getReader` + `TextDecoder` + `split('\n\n')` + 正则抠 `event:`/`data:`」，差异只在错误容忍度与超时处理——**正是这种"看着差不多"的复制最容易修 bug 时漏改其中一处**。净减 **175 行 → 36 行**。
    - 差异参数化：`errorPrefix`（各接口 400/500 文案，如「章节生成接口」——用户直接看到这句话）、`stoppedMessage`（默认「已停止生成」）、`tolerant`（`false` 供本地工作流：畸形 SSE 直接抛、错误尽早暴露；默认 `true` 供长对话流：单条畸形数据跳过、不杀死整条流）。`SSE_TIMEOUT_MS = 180000` 与 axios timeout 对齐。
    - **保留并集中了那条易踩的注释**：必须显式校验 HTTP 状态——后端 400/500 返回 JSON 错误体（不是 SSE），不校验就会拿它当事件流解析 → 前端"完全没有输出"、真实错误被吞（见 04-C13）。
  - **`frontend/src/composables/useSvgViewport.js`（新）**：抽出 `view{scale,tx,ty}` + `clientToSvg`（**`preserveAspectRatio="xMidYMid meet"` 的居中留黑边偏移换算——本 composable 的核心价值，两个视图都曾各自踩过这个坑**）+ `screenToContent` + `zoomAt`/`zoomBy`/`resetView` + `startPan`/`movePan`/`endPan`/`onWheel` + `contentTransform`/`zoomPercent`。常量化 `ZOOM_STEP=1.15` / `ZOOM_MIN=0.2` / `ZOOM_MAX=5`。`WorldMapView.vue` **106→57 行**、`CharacterRelationView.vue` **71→44 行**。
  - **顺带修掉 2 个真 bug**（都不是重构引入，是原本就存在的）：
    1. **两视图 `onSvgBlankClick` 量纲错误**：都把 composable 的 `dragStart`（**viewBox 内容坐标**）当**客户端像素**去算位移，`scale≈1 且 tx=0` 时两者恰巧接近才一直没暴露；一旦缩放平移，**"拖动平移"会被误判成"点击空白"**（清空选中/取消连线）。已在两视图各自本地记录 `panClientStart`（客户端像素）——**刻意不从 composable 取**，因为它给的是内容坐标、语义不同。
    2. **内容层 `<g>` 无稳定选择器**：给两个内容层补 `cr-content` / `wm-content` 类名（原先测试只能靠 `<g>` 序号猜，已实际踩中：WorldMap 的首个 `<g>` 是罗盘组，取错导致断言假失败）。
  - **真机验证（Playwright + 本机 Chromium，用户 8000/5173 全程未动）**：**20/20 全过** —— 两视图的 SVG 渲染、初始 100%、内容层 `matrix()`、放大→120%、缩小→回落、重置→`matrix(1,0,0,1,0,0)`、滚轮以指针为锚点缩放、拖拽平移（matrix 位移分量确实变化）、以及**「拖动空白不产生误判副作用」**。控制台仅剩**既有** favicon 404（已 curl 验证 5173/8000 均返回 404，纯外观问题、与本次改动无关）。验证用的临时脚本、临时作品（含 2 角色/1 关系/2 地点）已全部清理，作品数归 0。
  - **后端全量单测 144 passed**（纯前端改动，零回归）；`vite build` 通过（1737 modules）。
- **Phase 3.2 合并 `discussion.py` 两处 80 行重复（两阶段 LOAD_REFS 流式）**：
  - `/discussion/chat` 与 `/discussion/global-chat` 里**各存一份**约 80 行的两阶段参考加载 + 流式生成逻辑，**唯一差异只是日志前缀**——任一处修 bug 漏改另一处就是潜在缺陷，故抽成 `_stream_two_phase()`（`discussion.py` **896→859 行**）。
  - **接口设计**：`assistant_text` / `assistant_thinking` 由调用方**传引用**进去追加——调用方 `finally` 里要用它们持久化落库，传引用比返回值再拆包更稳（也避免合并后漏收集导致「对话没存上」）；返回值是观测增量 dict，调用方 `obs.update(...)` 后落 `discussion_load_logs`。
  - **顺带清掉两处已失效的局部赋值**（`ref_selector` 原先在两个入口各建一次，合并后统一在 helper 内解析）。
  - **新增 `tests/unit/test_discussion_stream.py` 13 用例**：用假适配器直接驱动生成器，锁死 4 条分支——短路（Pass1 即答，只 1 次调用）/ 两阶段（refs 事件 + 流式）/ Pass1 异常降级单次流式 / 无 `chat` 能力降级；外加思考内容透传、**LOAD_REFS 指令泄漏拦截**（模型偶发把协议指令写进正文）、观测 dict 三类取值。
  - **踩坑**：`LOAD_REFS`/`LOAD_SETTING` 正则只认**十六进制 id**（`[0-9a-f,\s]+`）。测试里用 `doc1`/`ghost`/`d1` 这类字母组合会被**静默忽略**（不报错、当成"模型没请求"）→ 首轮 3 例失败，换 `aa11`/`cc33` 后全过。**教训已记**：构造假 marker 数据必须用 hex id，否则「功能没生效」实为「id 根本没被解析」。
  - **真机验证**（8010 临时实例，用户 8000 全程未动）：① 全局对话短路路径 `context → chunk → done`（单次调用）；② 全局对话**两阶段路径** `context → refs（实载「古代官场·路级官僚体系」+「古代·官员俸禄与财富参考」2 份）→ chunk×N`，回答正确引用路级品级（正四品/常、从三品/要路）与年俸（280~840 两）；③ 项目商讨 `context → chunk → done`。临时作品已删除（作品数归 0）。
  - **全量单测 144 passed**（131 + 13 新增，零回归）；路由仍 139 条。
- **Phase 3.1 死代码清理（前端 638 行 + 后端 stubs 收窄）**：
  - **前端删除 11 个文件 / 638 行**（每个都先 grep 实证 0 引用再动）：`src/_deprecated/` 整目录 4 文件 448 行（`ChapterView`/`ConfigChatView`/`DiscussionView` + 其 README；config-chat 的能力已由 `ChatInput.vue` 承载，删的是不可达重复 UI，历史版本见 `git bd74768`）；3 个 0 引用组件 `ForeshadowTimeline.vue`、`RelationGraph.vue`（纯 `el-empty` 占位）、`ChapterElementsPanel.vue`（无调用方的薄包装）共 78 行；`TemplateDialog.vue` 76 行（同 0 引用，且含伪功能、被 `TemplateView` 的「规划中」页取代）；3 个 0 引用 API 模块 `api/foreshadow.js`、`api/memory.js`（与 `api/assist.js` 里的 `memoryApi` 重复且无人 import）、`api/template.js` 共 36 行。
  - **后端 `services/stubs.py` 收窄**：原 15 个函数中 **13 个实测 0 引用**（`create_project`/`list_projects`/`list_characters`/`create_character`/`run_command`/`list_chapters`/`list_discussion`/`clear_discussion`/`list_models`/`create_model`/`test_model`/`compress_memory`/`get_memory_summary`——各业务模块早已由真实 CRUD 实现，这些桩是脚手架残留），文件从 106 行缩到 39 行；仅保留仍被 `routers/template.py` 调用的 `list_templates` / `generate_outline`。**`outlines` 路由按 09-09 决策保留冻结，未动**（路由仍 139 条）。
  - **⚠️ 过程中踩中 04-A8（沙箱删文件连带清空同级目录）**：`git rm` 删 `components/workspace/` 内 1 个文件 → **整个目录 7 个文件消失**；`Remove-Item -Recurse` 删 `_deprecated/` → **连 `views/ store/ router/ layout/ utils/ styles/` 一起没了，累计误删 31 个文件**。全部源码都在 git 里，`git restore --source=HEAD --worktree --staged frontend/src/` 秒级完整还原（工作区内容从未真正丢失）。**已把处置铁律写进 04-A8**：删文件用单文件 `rm -f`；要让 git 记录删除用 `git update-index --force-remove`（纯索引操作、完全不碰文件系统）；删完立刻 `find -type f | wc -l` 核对；发现误删先 `git restore`，**切不可 `git add -A`**。
  - **验证**：后端单测 **131 passed**（清理前基线 131，零回归）；`main.py` 可完整加载、路由 139 条不变；前端 `vite build` 通过（1735 modules，7.89s）；起 8010 临时实例真机冒烟——`/health`、`/templates`（返回 7 条模板）及 `/projects` `/settings` `/global-skills` `/workflows` `/models` `/references/global` `/projects/x/outlines` **全 200**；验证后确认 PID 身份（94MB python.exe）再 taskkill，**用户 8000 后端全程未受影响**。
- **测试成本优化：写后摄取分阶段开关 + e2e 多轮省调用（用户拍板：fallback 兜底 / 默认全不动 / 第1轮按档 2~N 轮 none）**：
  - **问题**：跑一次全链路要 **3 次 LLM 调用**（正文 1 + 记忆抽取 1 + 概览聚合·篇级 1）。验证「文笔稳定性」时后两次对目标零贡献——跑 5 轮 = 15 次调用，其中 10 次白烧。（阶段压缩不满 10 章不触发，本就免费；去AI味是本地算的，不调模型。）
  - **新增 config 键**（默认全 True = 行为与改造前 100% 一致，零回归）：`memory.extract_enabled`（关掉改走 `fallback_extract` 规则兜底）、`memory.aggregate_overview`（关掉篇级概览改纯拼接）。
  - **`ingest_chapter` 加 `extract` / `aggregate` 参数**（None=读配置，显式入参优先）。**关键设计**：`extract=False` **不是整段跳过**，而是走规则兜底——章级记忆仍落库，走向/伏笔/篇章参考链路不断，只是摘要不如 AI 精炼。新增 `fallback_reason` 字段区分「主动省调用」与「LLM 失败」，否则日志会把省调用误读成抽取坏了。
  - **请求级 `ingest_level`**：`GenerateRequest.ingest_level` = full / lite（跳过聚合）/ none（全跳），经 `_background_ingest` 线程透传（只传字符串，守住「不传 ORM/session」铁律）。
  - **`test_full_chain.py` 加 `--ingest-level` / `--rounds` / `--verify-db` / `--seed-entities`**。`--rounds N`：第 1 轮按档全跑（验闭环+断言），2~N 轮自动 none（只 1 次调用验文笔），跑完打印各轮字数/耗时/重复率对照 + 波动率。**5 轮从 15 次 → 7 次**，加实体入库测试共 8 次。
  - **`--seed-entities` 补上此前完全没测的链路**：一次 `POST /command` 让 AI 抽四类实体全部入库（+1 次调用，并入第 1 轮）。**真机实测 4/4 非空**：characters=3 / factions=3 / locations=3 / relations=2。
  - **`--verify-db` 真机实测**：章级记忆 1 条 ✅ / 「篇章参考」文档 1 份且含 `<!-- ch:1 -->` 段（370 字）✅ / 实体 4 类非空 ✅。**顺带证实**用户记忆中的「生成的小说会存进参考文档」功能确实工作——`append_article_digest` 把每章**摘要**追加进名为**「篇章参考」**的作品内文档（不是「篇章摘要」，后者只是 tags 标签；我第一版断言按 tags 匹配导致 0 命中，已修）。
  - 测试：新增 `tests/unit/test_ingest_switches.py` **8 用例**；**全量单测 131 passed**。日志实证：第 1 轮 `fallback=False(llm)` + `dirs=3` + 概览聚合跑（篇=1 卷=1 小说=1）；第 2 轮 `fallback=True(extract_disabled)` + `dirs=0` + 「概览聚合已按 ingest_level 跳过」。
  - **清理**：删除残留空壳作品 `E2E-20260910-105326`（正文 0 字 / 无记忆 / 无参考，是失败生成的壳）。作品列表现为空。
- **Phase 2 收官（2.2 / 2.3 / 2.4 / 2.5 全部完成）+ config-chat 归档**：
  - **2.4 级联删除补孤儿**（先做，因为会留脏数据）：实测 4 处漏清——删角色后 `relations`（两端任一）/`skills.owner_id`/`locations.related_ids`/`factions.members`+`leader_id` 全指向已删角色；删章后 `chapter_memories` 残留（**危害最大**：后续章节还会把它注入上下文）；删篇漏 `chapter_memories`+`discussion_messages`+`reference_docs`；删卷漏上述全部。已在 `character_crud`/`chapter_crud`/`article_crud`/`volume_crud` 补齐。新增 4 用例（`_seed_four_levels` 造完整四级链），**全量 123 passed**。
  - **2.2 章节列表接线**：`ChapterListView.vue` 从「规划中」占位重写为真实页面——树形表格（卷→篇→章，复用 `store.structure`，与侧栏同源不重复请求）、关键词搜索（标题+正文）、状态筛选（全部/已写/草稿）、单章改名、单章删除、多选批量删除（逐条 DELETE，失败汇总不影响其余）、「进入」跳对话页。**顺带补了侧栏入口**——该路由原为 `hideTab: true` 且侧栏无菜单项，等于接线完也点不到（与 config-chat 同类问题）。
  - **2.3 走向卡片补真正的断点**：卡片渲染/落库链路之前已通，但点卡片只在**当前章**线程发消息，而卡片说的是「第 N 章写完、接下来怎么走」——消息落进旧章，作者还得手动切。现 `onPickDirection` 先用 `findNextChapter`（跨篇按 `chapter_no` 取最近下一章）自动切章再发送。
  - **2.5 对话可中断**：`discussion.js` 两个流函数支持外部 `signal`（与内部超时 controller 合并）；store 新增 `_discussionController` + `stopDiscussion()` + `_appendStreamError()`（停止时保留已流出内容 + `stopped:true`，**不再写「发送失败」红字**）；`ChatInput` 回复中「发送」变「停止生成」；`ChatPanel` 加中性灰尾注。后端 `openai_compat.stream` 读超时 **240s→90s** 并单列超时文案（原来模型卡住要干等 4 分钟）。前端 `vite build` 通过。
  - **config-chat 归档**：316 行真实功能但侧栏零入口 → `ConfigChatView.vue` 移至 `src/_deprecated/`（附 README 说明复原方式），`router/index.js` 摘掉路由与 import。**能力未丢**：`/角色 /地点` 等斜杠指令 + 自然语言入库已由 `ChatInput.vue` 承载（同调 `commandApi` + `parseSlashCommands`）。
- **Phase 1 收尾（1.3 / 1.4 / 1.5）**：
  - **1.3** `api/chapter.js:generateChapterStream` 补 `resp.ok` 校验。裸 `fetch` 此前不校验状态码，后端 400/500 返回的是 JSON 错误体（非 SSE），被当事件流解析 → **前端"毫无输出"、真实错误被吞**（记入 04-C13）。现读 `detail/message` 后抛错，并补 `resp.body` 空判断。
  - **1.4** `/validate` 改为显式 **501**。原走 `stubs.validate_settings` 恒返回空 issues = **假绿灯**（界面显示"校验通过、零问题"，比没有更危险）。顺带删除已无调用方的 `stubs.validate_settings` 与前端死代码 `validateApi`。生成链路里的 `validate` SSE 事件（去AI味）未受影响。
  - **1.5** 删 `direction` 路由 + `views/DirectionView.vue`（模块已删）；新建 `components/common/PlannedFeature.vue`，把 3 个**假 UI 占位页**（伏笔 / 章节列表 / 套路模板）统一改成诚实的「规划中」页（原先空表格带"查看/备注"按钮、能点的模板卡片，看着像"功能有了只是没数据"）；措辞按事实校准（章节列表是后端已就绪、前端未接线）。前端 `npm run build` 通过。
- **Phase 2.1 伏笔回注（补齐"最后一米"，闭环贯通）**：新增 `services/foreshadow_crud.py`——`sync_from_actions()` 把每章的 `foreshadow_actions` 回注进 `foreshadows` 表（bury→新建 pending / hint→关联场景 / resolve→标记 done + activated_chapter；模型报了没登记过的回收则建 done 记录留痕）；`ingestion` 新增 **2.6 步**自动回注；7 个伏笔路由从桩转真实（`detect` 保留为显式 501——识别已自动完成）。**关键背景**：`core/context/layers.py:layer_foreshadows` 的读路径早就写好了，只是表里永远没数据——所以补完写入侧，闭环立刻贯通。**踩两个坑并修复**（均记档）：① `session autoflush=False` 下 `add()` 后必须 `flush()`，否则同批后续匹配查不到刚加的记录 → 重复建（04-C14）；② 模糊匹配阈值缺长度门槛：短描述差 1 字比率就 0.833，会把两条独立伏笔并成一条 → 加 `_SIM_MIN_LEN=12` + 阈值 0.85（04-C15）。**单测 15 用例全绿**。**真机闭环验证**：第 1 章生成 → 摄取抽出 2 条伏笔 → 落 `foreshadows`（pending / 埋于第 1 章）→ **第 2 章生成上下文出现【伏笔状态】块并列出这 2 条**。
- **测试**：单测累计 **119 用例全绿（~9s）**；路由仍 139 条。

- **⚠️ 事故与恢复：沙箱内 `git rebase` 破坏 `.git`（记入 04-A7）**。推送 B 线提交时被拒（远程有用户 13:56 在 GitHub 网页上改的 README 提交 `33c5656`），随后执行 `git rebase` 报 `could not mark as interactive`，`.git/refs/` 目录被抹掉、刚提交的 `d519666` 与新 fetch 的对象一并丢失，git 报 `not a git repository`。**恢复**：备份 `.git` → 重建 `refs/` 目录（git 立刻恢复识别）→ 确认 pack 历史断在 `878ff45` → 以远端为准重建本地仓库（`mv .git .git.corrupt` → `git init` → `fetch` → `update-ref main` → `reset --mixed`）→ 工作区变更完好，重新提交为 `c395a2f` 并推送。**工作区文件全程未受影响**（沙箱只搞 `.git`）。教训已写入 04-A7：沙箱里禁用 `git rebase`、动手前先 `cp -r .git`、push 前先 `ls-remote` 对表、保持随时 push。
- **B 线工程卫生五项完成（0.2 / 1.1 / 1.2 / B4 / 2.6）**——用户拍板按「1.2 → 1.1 → B4 → B2 → B3」顺序开工，孤儿数据选「清掉」。
  - **1.2 错误提示不得落库成正文**（复核确认仍是活 bug）：新增纯函数 `_can_persist(full, error_notes)`；错误/占位文案改存 `error_notes` 只推前端展示，不再进 `content_parts`；正文为空则不落库、只发 `error` 事件（不发 `saved`）。**顺带修掉一个隐蔽的数据丢失**——原先「重新生成」失败时会把已有章节正文整段覆盖成错误提示。前端补 `error` 事件处理（不误报"生成完成"，留在表单可直接重试）。测试 8（纯函数）+ 2（**真实驱动 SSE 生成器**：必抛异常的假适配器 → 不建章 / 不覆盖原稿）。
  - **1.1 隐私日志清理**（实测残留比记录更多，共 5 处）：后端 `discussion.py` 逐条打印 messages 正文前 160 字（原记录误以为只打"条数"）、`assist.py` 打印模型原始返回前 1000 字；前端 `store/project.js` 两处（用户输入全文 + 各 ID、history 逐条正文前 120 字）、`api/discussion.js` 两处（完整 Body + 最后一条消息 + system prompt）；gateway 调试落盘（见 C11）。保留 `console.error` 类无内容诊断。
  - **0.2 print → logging**：实际 **82 处 / 16 文件**（原记录 64 处，A 线新增约 19 处）。新建 `core/logging_config.py`（`时间 级别 [模块] 消息`、`NA_LOG_LEVEL` 可控、uvicorn 不重复打印、第三方库压 WARNING），`main.py` 启动即 `setup_logging()`（**不调用的话 INFO 会被 last-resort 处理器静默丢弃**）。按语义分级（失败/异常/降级/跳过 → warning），自动剥离 `flush=True`（logging 不接受）。**顺带清掉 C11**：`openai_compat.stream_with_thinking` 残留调试块把模型输出样本写进 `backend/glm_sse_raw.log`（隐私泄漏 + 硬编码绝对路径 + 每次流式白耗 IO），已移除并删除残留文件。
  - **B4 删除 `directions` 全链**：ORM 类 / `routers/direction.py`（3 条桩路由）/ `schemas/direction.py` / 前端 `api/direction.js`（零引用死文件）/ 因之孤立的 `stubs.recommend_directions` / DB 表（0 行）。**能力未丢**：ingestion 每章的走向卡片走 `meta.type=post_chapter_directions`，`ChatPanel.vue` 渲染逻辑未动。路由 142 → 139。`outlines` 按 09-09 改判**保留冻结**，未删。
  - **2.6 孤儿数据清理 102 行**：articles 20 / chapter_memories 33 / reference_docs 21 / volumes 18 / chapters 5 / discussion_load_logs 5。流程 = 备份 `novel_agent.db.bak.20260910_135942` → 导出 `orphans.json` → 事务删除 → 校验（孤儿 0、全局池 18 份资料与 133 向量块未动）。**踩中 C12**：「project_id 不在 projects 里」会把 `__global__`（全局资料池 + 全局对话）判成孤儿，差点删掉 133 个全局向量块使全局检索报废 → 所有表统一豁免 `__global__`。
- **测试工具修正**：`test_full_chain.py` 的字数下限改为按 `--target-words` 等比折算（原硬编码 1800 导致 `--target-words 1500` 时正文 1463 字被误判失败）。**单测累计 104 用例全绿（~7s）**；B 线后 e2e 实机回归通过（`saved` 正常、落库与流式一致 1623=1623、去AI味 100）。

- **A6 按需加载两阶段协议 e2e 落地（`services/entity_graph.py` 收尾后 A 线收官）**：新增 `tests/e2e/test_on_demand_load.py`，**9/9 通过**。**防幻觉设计**是关键——问题答案取「只有资料里才有且不可猜」的事实（自造剑碑名「照胆」+ 任取兑率 137×64=8768），答对即证明正文真的注入了。覆盖三条路径：① **商讨真两阶段**：Pass1 同时输出 `LOAD_REFS`+`LOAD_SETTING` → `refs` 事件 `loaded=[太虚剑宗剑碑名录.md, 灵石货币体系]` → Pass2 答出「照胆」「8768」；② **短路路径**：常识问题无 `refs` 事件、单次调用即答；③ **章节 hybrid 确定性 top-up**：要点须含全局池标签才触发（`score_reference>=4`），实测 `ref_mode=hybrid`、补入「地名·自然山川与秘境」「地名·建筑与场所」并推 `refs` 事件。踩坑：首轮 S7 被 SKIP，误判为「环境变量没生效」，实为测试要点未命中全局池标签——`_global_topup_ids` 的阈值设计使然，改要点后即通过。
- **修出第三个真缺陷 C9（异步摄取 vs 删除作品竞态）**：全流程 e2e 后巡检发现 `vec_index` 比 `vector_chunks` 多 2 行孤儿块，project_id 指向刚删掉的 e2e 作品。根因：写后摄取是**异步后台线程**，作者在摄取完成前删作品 → 级联清理先跑 → 摄取随后把向量写进已不存在的项目。危害放大点：`vec_index` 是全局表，孤儿块永久挤占所有项目的 KNN 名额（与 C7 同源）。修复：`vector_index.index_chunks`（所有向量写入的唯一咽喉）加项目存在性守卫，不存在则直接返回 0（置于 embedding 之前，顺带省 API）；`__global__` 虚拟 project_id 豁免。回归用例覆盖「不存在项目跳过 + 全局池放行」。已清理现存 2 块孤儿。记入 `docs/04` C9。
- **e2e 全流程回归（对用户实机 8000）**：① `test_full_chain.py` **8/8 全绿**——2019 字 / 59.6s / 首字 33.7s / 标点密度 0.116 / 最长无标点段 18 字 / 拉丁 0 / 3-gram 最大重复 7 / **去AI味 100** / 级联清理 404 复核干净；② `test_retrieval_chain.py` 检索链路全通——实体图带出玄真子/苏清月/太虚剑宗/城隍庙/太虚剑宗山门，4/4 参考全召回（C7 修复在实机确认），正文用上扩展实体；③ `test_on_demand_load.py` 9/9。**累计单测 94 用例全绿（~8s）**。
- **测试基建**：`tests/README.md` 登记 `test_on_demand_load.py` + 「改了按需加载跑什么」一行。

- **A 线激活（用户提供 key + 重启后端）**：key 写入 app_configs `retrieval.siliconflow_key`；`vector_chunks`/`vec_index` 表经 `init_db` 自动建成；全局资料池 18 份文档 reindex → **133 向量块**；`SqliteVecStore` 生效（非暴力回退）。真机验证：embedding API 直连 OK（1024 维、L2 归一化、语义 cos 0.49）；`search_similar` 语义命中验证（query「门派名字」→ 命中「势力名称·玄幻修仙」文档，字面零重合）；`pick_relevant` 双通道 + 删除清向量（作品删干净、全局池 133 块不受影响）全链跑通。
- **检索升级 A4 rerank 重排落地**：新增 `rerank_client.py`（硅基流动 BAAI/bge-reranker-v2-m3，纯 stdlib，与 embedding 共用 key，批量 ≤64 自动分批 + 全局下标还原，失败抛 `RerankError`）；`pick_relevant` 在 RRF 后接重排——RRF 取 top_k×3 候选 → rerank 逐对打分 → 取 top_k；rerank 失败静默降级 RRF 原序；候选数 ≤top_k 时跳过（省 API 调用）。明细新增 `rerank_score`。**真机实测区分度**：RRF 把关键词未命中的「势力名称·玄幻修仙」排第 3（0.0164），rerank 给 0.0724 **提回第 1**；而 bge-m3 余弦在该场景密集在 0.5249/0.5093/0.4975（差 0.007 无法排序）——验证了 retrieve-then-rerank 的必要性。**单测 8 用例全绿，累计 79 用例全绿（~5s）**。
- **文档同步**：03 Phase R 表 A4 ✅ + 激活状态、02 §1.1 加 A4 与端到端激活两行、05 §6.5 加 rerank_client + 融合检索描述更新 + 环境变量 `NA_RERANK_MODEL`。
- **下一步**：A5 GraphRAG（复用 characters/relations/factions/locations 表）→ A6 e2e 覆盖 LOAD_REFS/LOAD_SETTING 全流程。

- **检索升级 A5 实体图一跳扩展落地（GraphRAG）**：新增 `services/entity_graph.py`——把已有四张表当**异构图**：角色→角色（`relations` 双向，按 strength 降序、上限 10）、角色/势力→势力（`factions.members` 支持名字或 id、`leader_id`）、势力→掌门、角色/势力→地点（`locations.related_ids`）。扩展出的实体**提升为「本章重点实体」**，交给现有 layers 按全量渲染（此前只有「主角 + 要点点名」才全量，邻居全被降级成一行简写 → AI 写「回宗门搬救兵」时只能现编）。**刻意不递归**（两跳会连通全作、撑爆窗口）；`retrieval.graph_expand` 开关（默认开）；trace 进 `context` 事件 `entity_graph` 字段（可观测）。**单测 11 用例全绿**（关系双向/成员三形态/掌门/关联地点/上限/幂等/异常静默）。**离线实测**：提示词只点「沈砚」→ 带出玄真子(师徒90)/苏清月(道侣85)/太虚剑宗/城隍庙/太虚剑宗山门，全部进入上下文正文；陆离（离沈砚两跳）正确地未纳入。
- **新增 `tests/e2e/test_retrieval_chain.py`（A 线检索验收脚本）**：造实体图 + 导入全局参考 → 只点一个名字生成 → 断言并打印 `context` 事件里的「实体图扩展 / 最终命中实体 / 参考命中明细（kw/vec/rerank 分）/ 扩展实体在正文出现次数」。与 `test_full_chain.py`（生成质量基线）分工互补。
- **真机 e2e 抓出并修掉两个真缺陷**：① **C7 向量索引全局表跨项目稀释召回**——`vec_index` 是所有作品 + 全局池共用一张表，旧实现靠 `k=top_k*3` 全局过采样再回表过滤，本项目 4 份资料只召回 1 份（全局池 133 块把 top-k 吃光）。修复：`vec_index` 加 `project_id`/`source_type` **辅助列**，KNN 查询内直接过滤（sqlite-vec v0.1.9 元数据过滤）；旧 schema 启动时自动删表重建 + 从 `vector_chunks` 自愈回填；回归用例「干扰项目塞 200 同向块，本项目 3 块必须全召回」。修复后 e2e 4/4 全召回。② **C8 作品级联删除漏清向量**——删作品后 `vector_chunks` 残留 10 块（表未登记进 `_RELATED`、`vec_index` 是虚拟表根本不走 ORM 级联）。修复：`delete_project` 显式调 `vector_store.remove_project_index`（主表 + 虚拟表一起清）。两坑均记入 `docs/04` C7/C8。
- **A5 真机效果**：第二轮 e2e 生成 **1244 字 / 18s**（首轮 655 字，修好召回后上下文更充分）；正文实际用上了扩展实体（苏清月 9 次、幽冥殿 4 次、陆离 3 次、太虚剑宗 1 次、城隍庙 1 次）。**累计 93 用例全绿（~7s）**。
- **测试基建**：`tests/README.md` 更新（新增检索链路脚本说明 + 「起临时后端跑 e2e」小节：`PORT=8010 DEV_RELOAD=0 dev.py` 不动手头的 8000）。

- **检索升级 A 线 A1+A2 落地（用户拍板"一步到位"，不搞 numpy 暴力起步）**：① `embedding_client.py`——硅基流动 BAAI/bge-m3（1024 维，L2 归一化，纯 stdlib 零新依赖），key 三级查找（env `NA_SILICONFLOW_KEY` > app_configs `retrieval.siliconflow_key` > 模型配置表 vendor=siliconflow）；② `vector_store.py`——**VectorStore 协议 + 双实现**（SqliteVecStore 主实现 = sqlite-vec vec0 KNN + 回表过滤；BruteVectorStore 自动回退 = 纯 Python 余弦无 numpy），未来换底座 = 新实现类 + 工厂改一行；③ `vector_index.py` 编排层（段落切块 500 字 / 索引 / 删除 / 检索，全链失败静默降级）；④ `vector_chunks` ORM 表 + `vec_index` 虚拟表（database.py 挂 connect 事件加载 sqlite-vec 扩展，init_db 自动建表失败不阻断启动）；⑤ 写后摄取 3.5 步钩子（章级记忆 + 篇章摘要向量化）。**单测 12 用例全绿**（双实现契约：upsert/KNN/隔离/幂等/删除/排序一致）。踩坑两个：ORM merge 同 PK 同事务下发两条 INSERT 触发唯一约束 → 改 SQLite 原生 `INSERT OR REPLACE`；函数签名引用下方才定义的 dataclass 报 NameError → dataclass 前置。
- **检索升级 A3 Hybrid 混合检索落地**：`pick_relevant` 改为关键词 + 向量双通道 RRF 融合（k=60 标准参数，只用名次不用原始分，两路量纲无需调权）；向量通道为空（未配 key/未建索引）时行为与旧版**完全一致**；命中明细新增 `kw_score`/`vec_score`/`channels` 字段。**补齐参考文档向量生命周期**：上传/导入全局资料 → 自动建索引（此前只有篇章摘要在摄取时建索引，用户上传的文档从未入向量库——A3 必补缺口）；删除 → 同事务清向量块；新增 `POST /projects/{pid}/references/reindex` 存量补建端点（配置 key 后调一次即可）。**单测 8 用例全绿**（兼容性/向量独有命中/双通道排序/保底/摘要置顶/生命周期/reindex），**累计 71 用例全绿（~4s）**。文档同步：03 新增 Phase R 表 + §3 状态更新、02 §1.1 两行 + §3 待验证行、05 §6.5 向量检索层 + 路由 83 条 + 表 24+1、环境变量补 `NA_SILICONFLOW_KEY`/`NA_EMBED_MODEL`。
- **A 线激活三步（待用户）**：① 后端重启（建 `vector_chunks`/`vec_index` 表 + 加载新代码）；② 配硅基流动 key（env `NA_SILICONFLOW_KEY` 或 app_configs `retrieval.siliconflow_key`）；③ 调一次 reindex 补建存量索引。未配置前一切静默降级，生成链路行为与现状一致，无风险。

---

## 2026-09-09

- **文档体系重建**：旧文档（README 旧版 / API接口规范 / PROJECT_REQUIREMENTS / 架构设计 / 代码结构说明 / 全局库注入指南 / 接口与组件文档 / 两份体检报告 / 1 份 worklog）全部移入 `docs/_archive/`。
- **新建 6 份权威文档**：`docs/01-项目目标.md`、`02-已实现清单.md`、`03-规划与进行中.md`、`04-踩坑档案.md`、`05-架构与接口.md`、`06-AI工作手册.md`。
- **02 做了真机实测**：后端真机启动，逐端点 curl 验证 34 个端点，实测确认——伏笔 CRUD 为桩（POST 返回 `fs_placeholder` 但 GET 查不回）、`/validate` 为假绿灯（恒返回空 issues）、`/command` 指令入库真实可用、章级记忆 33 条真实。
- **历史日志归档**：`.workbuddy/memory/` 下 2026-08-06 ~ 08-14 共 9 份日志（294KB）移入 `_archive/`，坑点已提炼至 `docs/04`。`MEMORY.md` 精简为指针。
- **路线决策**：确认走"切片式重写"，不另起炉灶。模块去留：保留伏笔并补齐写入；删除 `directions` 与 `outlines`。
- **纠偏**：此前报告把 6 张 0 行表统称"空壳"有误——实际真空壳只有 `directions`/`outlines`；`foreshadows` 是"有读无写"断链；`skills`/`app_configs`/`stage_summaries` 均为真实现（0 行源于未使用 / 未触发 / 走默认值）。
- **孤儿数据排查（用户报"8 章"存疑）**：`project_id` 差集取证，确认 62%~91% 行数是 21 部已删作品的历史残留；`characters/relations/factions/locations` 孤儿为 0（因为在旧级联列表内）。**实测新建→塞数据→删除→残留 0，当前级联删除是干净的** → 结论：不改代码，只清一次数据（见 03-2.6，清理前备份）。已写入 02 §6 与 04-D6。
- **用户四点纠正，已全部落地**：① 题材改为**题材无关**（多题材适配），原"架空王朝探案"只是测试用题材；② **推翻"套路模板价值最低"的判断**——流水线/量产网文最需要套路模板，`outlines` 由 ❌删除 改判 ⏸冻结，方向是做成可编辑/题材中立的 structured data；③ 检索由"不做 RAG"改判 **待优化**（硅基流动免费 Embedding → 向量库 → 部分场景 GraphRAG → Hybrid 混合检索，见 01 §5.1）；④ 工作流改为**方案待定，三不：不投入/不删除/不扩展**（见 01 §5.2）。
- **06 新增两条常见误判**：行数 ≠ 真实产量（先做差集）；"功能价值低可删"前必须先确认服务哪种创作模式。
- **孤儿数据导出（按用户"先导出、不删、不迁"原则）**：DB 已备份（`novel_agent.db.bak.20260909_200949`，864 KB）+ 98 行全量导出到 `.workbuddy/memory/_orphan_export/`（5 章正文 + 18 volumes + 20 articles + 29 chapter_memories + 21 reference_docs + 5 load_logs）。**DB 一行未动**，决策权保留。
- **多 agent 协同方案落地**：新建 `docs/07-多agent协同手册.md`（轻量协同架构：调度 WB 分诊 + 任务卡 + 共享文档）+ `.workbuddy/tasks/` 目录（任务卡规范）+ 第一张示范卡 `2026-09-09-phase0-pytest骨架.md`（适合 OpenCode）。**零代码、零新基建、纯文档协同**。登记入 03 §3.2。
- **多 agent 方案定稿为「主力单干 + 投递单」**：调研现成编排框架（Agent Orchestrator / AI-Coding-Tools-Collaborative / um-agent-orchestration / groq-orchestrate 等）后确认——它们均要求 agent 可被 CLI spawn，而本组合只有 OpenCode 满足，WorkBuddy/TRAE/Zcode 不可编程驱动 → **放弃框架路线**。07 重写为 `docs/07-任务分发手册.md`（旧版归档 `docs/_archive/`）；03 §3.2 同步；06 索引更新；`.workbuddy/tasks/README.md` 与示范卡改写为新投递单格式。规则：主力单干，任务积压时 AI 出「投递单」（自包含、文件不重叠、铁律前置），用户当邮差粘贴分发。
- **测试基建统一 + 一键 E2E 全链路测试落地**：① 新建 `backend/tests/`（e2e/unit/reports 三区 + README 规范：以后测试脚本只许写这里），散落的 `_probe_pipeline.py`/`_smoke_startup.py` 迁入 `tests/e2e/` 并修 sys.path；② 新写 `tests/e2e/test_full_chain.py`——HTTP 注入式：健康检查→默认模型→建作品/卷/篇/章→SSE 真实生成 2500 字→质量指标（字数/速度/标点密度/最长无标点段/拉丁字母/3-gram/段首重复/错误标记/去AI味分）→写后摄取验证→自动清理→报告落盘 `tests/reports/`。**真机 3 轮**：链路全通，第 3 轮全绿基线（2566 字/123 字每秒/去AI味 99.6）；发现①生成内联 validate 是活的（报 6~14 issues，与 /validate 端点假绿灯是两段代码）；②长生成有句式循环风险（3 轮 1 触发），后端循环检测安全网有效截断。02 §1.1 已记录。
- **默认模型换 Qwen/Qwen3.8-Flash-Next + 修复特判失配（04-B10）**：用户换默认模型后 e2e 实测暴露——3 处 `"qwen3.5" in model` 字面量特判（chapter.py 惩罚归零、chapter.py+openai_compat.py 强关 thinking、workflow_engine/common.py）对新模型全部失配，惩罚回落 0.4/0.4 + thinking 未关 → 实测退化（首字 407s、标点密度 0.013、最长无标点段 1870 字、5 字/秒）。**修复：4 处匹配放宽为正则 `qwen3\.\d`**。另：9 次调用之谜已解——每轮 e2e 实为 3 次调用（正文生成 + 摄取抽取 + **概览聚合篇级摘要**，最后一项 auto 模式下调 LLM 且最易被忽略）。检索模型选型已定并记录：Embedding = 硅基流动 BAAI/bge-m3，Rerank = BAAI/bge-reranker-v2-m3（写入 01 §2/§5.1、03）。
- **修复后处理复读误杀（04-B11 新坑）+ thinking 策略改"尊重显式指定"**：用户要求开 thinking 验证 → 发现字数暴跌假象（DB 989 vs 流式 1843）→ 逐层取证：`_dedup_trailing_repeats` 用**字符集 Jaccard** 判段落相似，超短段差一字即爆 0.85（「沈砚看水洼。」vs「沈砚看向水洼。」=0.857），单段相似即全裁 → 实锤误杀 97 段正常剧情（0 段真重复，含收尾钩子）。**重写为三重防线**：短段<20字不参与 + difflib 内容敏感相似度（Jaccard 仅作预筛）+ 连续≥3长段才算复读；离线 4 用例全过（误杀场景不裁/真复读照裁）。**thinking 决策改为尊重显式指定**（chapter.py + openai_compat.py 两处，默认仍关、请求显式 on 则尊重；路由层 `_content_only_stream` 保证 reasoning 不进正文）。**最终验证轮全绿**：Qwen3.8-Flash-Next + thinking on + 惩罚 0 → 1894 字达标、流式落库一致（2082=2082）、质量全绿。e2e 脚本新增 `--thinking on/off` 参数与流式/落库不一致自动存档。
- **Phase 0.1 单测骨架 Plan A（12 用例）+ 修出 B12**：pytest 9.1.1 入 `.venv`；`backend/pytest.ini` + `tests/conftest.py` + `tests/unit/`（dedup 5 / humanizer 4 / smoke 3）全绿 0.76s；dedup fixture 直接用当晚 3 份真实轮次文本。**B12**：单测暴露 `_dedup_trailing_repeats` 只向前文比较 → 正好 3 段的复读块永远裁不掉（块首必判 False，4 段才够数）→ `_is_dup` 增加"或与紧邻后一段相似"，3 份真实文本回归零误杀。教训：边界用例必须测"恰好达到阈值"。
- **Phase 0.1 完整版（Plan B，51 用例全绿 1.6s）**：`test_db` fixture（monkeypatch 改 `dbmod.DEFAULT_DB_URL` + 重置 `_engine`/`SessionLocal` 惰性单例，零生产代码改动，真实库零风险）；新增 `test_gateway_payload.py`（12 用例：qwen/zhipu/nvidia/deepseek/o 系/GLM-5.3-Flash 各厂商 payload 形态固化 + broken combo 安全网）+ `test_sse_stream.py`（10：`_sse` 帧契约 / `_content_only_stream` close 传播 / `_RepetitionGuard` 双层检测含跨 chunk 劈句）+ `test_ingestion_json.py`（11：`parse_json_loose` 四种脏输出 + 边界）+ `test_cascade_delete.py`（4：全链级联 0 残留 / 删除作用域 / fallback 摄取路径顺带覆盖）。
- **默认模型换魔搭 GLM-5.3-Flash + 修复 stream() 漏兜底（04-B13）**：e2e 实测 91.2s "正常"走完但 **0 chunk / 正文 0 字**。20 行探测脚本直连取证：**773 帧 content_len=0，正文全进 reasoning_content（1418 字）**，且 `thinking.type` 被魔搭静默忽略（不报错不生效）——GLM 系已知行为（NVIDIA NIM GLM-5.2 同款），但 `chat()`/`stream_with_thinking()` 都有 reasoning 兜底、**唯独章节生成的 `stream()` 漏了**。修复：stream() 补兜底 + 英文占比 >15% 拒绝防线（Qwen3.x 的英文分析不污染正文；Qwen3.x content 正常出、不受影响）。
- **GLM-5.3-Flash 终局：三层问题链定案，不适合章节正文（04-B13 续）**：① content 排在 reasoning 之后被 max_tokens 预算卡死（三档探测实锤：mt=800→content 仅 80 字 finish=length；4000/16000→正文正常）→ 用户拍板按次计费不省 token，chapter.py 对 GLM 系直接给 32768（实测接受）；② 32768 预算下字数达标（2229）但**去AI味 0 分**——GLM 把英文元认知自我审查写进 content 正文流（"Wait—I wrote an internal reasoning slip above..."）+ 中文无标点连排 508 字，**模型行为应用层无解**；③ 决策建议：默认章节模型换回 Qwen/Qwen3.8-Flash-Next，GLM-5.3-Flash 留作商讨/短问答。另：test_full_chain.py 加 `install_opener(ProxyHandler({}))` 禁系统代理（Clash 劫持 127.0.0.1 回 502 假象，与 curl --noproxy 同理）。
- **Phase 0.1 单测骨架落地（Plan A）+ 单测当场抓出真缺陷（04-B12）**：安装 pytest 9.1.1 → `backend/pytest.ini` + `tests/conftest.py`（刻意不建 DB fixture：DEFAULT_DB_URL import 时绑定，注入测试库需先重构配置读取时机，转 0.1b）→ `tests/unit/` 3 文件 12 用例（去重反误杀×5，fixture 直接取自当晚 3 份真实轮次文本；去AI味×4；路由装配冒烟×3）。全绿过程中 `test_constructed_repetition_is_cut` 连挂两次：第一次是测试素材缺陷（body 段只差序号互相成复读），第二次**暴露 `_dedup_trailing_repeats` 真缺陷**——`_is_dup` 只向前文比较，复读块「块首」前文全是正常文本必判 False，导致正好 3 段的复读块永远裁不掉（run 只能数到 2，需 4 段才够数）。修复：`_is_dup` 增加「与紧邻后一段相似」判定（同样过 ≥20 字 + Jaccard 预筛 + difflib 三道门），3 段复读块可裁且 3 份真实文本零误杀。**教训：单测用例要同时覆盖「该裁的」边界（恰好 RUN 段），不止「不该裁的」**。
