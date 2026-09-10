# backend/tests — 测试脚本统一目录（规定：以后所有测试脚本都在这里写）

> 立规日期：2026-09-09。此前散落的 `backend/_probe_pipeline.py`、`backend/_smoke_startup.py` 已迁入本目录。

## 目录结构

```
backend/tests/
├── README.md            ← 本文件（规范）
├── conftest.py          ← pytest 全局配置（sys.path 兜底 + test_db fixture：独立临时 SQLite）
├── e2e/                 ← 端到端测试（HTTP 注入式 / 直接 python 跑）
│   ├── test_full_chain.py    一键全链路：建作品→卷→篇→章→真实生成→质量报告→清理
│   ├── test_retrieval_chain.py  A 线检索验收：造实体图→只点一个名字→验证 GraphRAG/
│   │                         关键词/向量/RRF/rerank 是否真把该给的资料给了模型
│   ├── test_on_demand_load.py  A6 按需加载验收：LOAD_REFS/LOAD_SETTING 两阶段协议
│   │                         （含短路路径 + 章节 hybrid top-up；答案取"不可猜"数值防幻觉）
│   ├── probe_pipeline.py     内部管线探针（假模型适配器 + 临时 DB，不碰真实数据）
│   ├── probe_glm_ms.py       魔搭 GLM 原始 SSE 帧探测（换新模型时先跑这个，key 走环境变量）
│   └── smoke_startup.py      启动冒烟（路由装配 + 建表 + SKILL 安装）
├── unit/                ← pytest 单元测试（2026-09-10：119 用例全绿 ~9s）
│   ├── test_dedup.py         去重反误杀回归（fixtures/ 内 3 份真实轮次文本）
│   ├── test_humanizer.py     去AI味打分回归
│   ├── test_smoke.py         路由装配冒烟（import main，零 DB 副作用）
│   ├── test_gateway_payload.py  各厂商 payload 组装形态（GLM-5.3-Flash/Qwen/思考字段/惩罚）
│   ├── test_sse_stream.py    SSE 帧契约 + close 传播 + RepetitionGuard 双层检测
│   ├── test_ingestion_json.py   parse_json_loose 容错（围栏/废话/尾逗号/全角引号）
│   ├── test_cascade_delete.py   级联删除 0 残留（含摄取 fallback 降级路径）
│   ├── test_vector_store.py   向量存储双实现契约 + 全局表元数据过滤 + 竞态守卫
│   ├── test_pick_hybrid.py    关键词+向量 RRF 融合 + 参考文档向量生命周期钩子
│   ├── test_rerank.py         rerank 客户端 + 集成（重排生效/失败降级/候选不足跳过）
│   ├── test_entity_graph.py   实体图一跳扩展（关系双向/势力归属/掌门/关联地点/上限）
│   ├── test_chapter_persist_guard.py      1.2 纯函数：正文为空则禁落库
│   ├── test_chapter_failure_no_persist.py 1.2 集成：真实驱动 SSE 生成器，模型失败不建章/不覆盖
│   ├── test_foreshadow_sync.py 2.1 伏笔回注：bury/hint/resolve 语义 + 去重幂等 + CRUD
│   └── fixtures/             ← 测试素材（真实章节文本，勿改）
└── reports/             ← 测试报告输出（test_full_chain.py 自动写入，可删）
```

## 规则

1. **所有测试脚本只放本目录**。禁止再往 `backend/` 根或其他地方塞 `test_*.py` / `*_probe*.py` / `smoke_*.py`。
2. **e2e 测试对着已启动的后端跑**（默认 `http://127.0.0.1:8000`），不自己起服务；unit 测试不依赖后端进程、零网络零 DB。
3. e2e 测试**自带清理**：创建的测试作品跑完即删（除非 `--keep`），不留孤儿数据。
4. 涉及真实模型生成的测试**耗时 1~5 分钟**，属正常；质量指标阈值以 `docs/04-踩坑档案.md` B 类坑为依据（标点密度 / 最长无标点段 / 拉丁字母 / 重复率）。
5. 运行方式统一：
   ```bash
   cd E:/AI小说创作/backend
   # unit（秒级，提交前必跑）
   E:/AI小说创作/.venv/Scripts/python.exe -m pytest tests/unit/
   # e2e（分钟级，改生成链路后跑）
   E:/AI小说创作/.venv/Scripts/python.exe tests/e2e/test_full_chain.py
   ```
6. 测试发现 bug → 先记 `docs/04-踩坑档案.md`，再修代码；测完更新 `docs/02-已实现清单.md`。
7. ~~unit 需要 DB 的场景先重构 config 再建 fixture~~ **已完成（2026-09-10）**：`test_db` fixture 用 monkeypatch 改 `app.core.database` 模块的 `DEFAULT_DB_URL` + 重置惰性单例实现隔离，零生产代码改动；需要真实模型调用的才走 e2e。
8. 接入新模型：先跑 `probe_glm_ms.py`（改 model 名）看原始 SSE 帧字段分布，再决定适配（见 04-B13——官方文档的响应结构说明不可信，第三方兼容层各有魔改）。

## 何时跑什么

| 场景 | 跑什么 |
|---|---|
| 改了去重 / humanizer / 任何纯函数逻辑 | `pytest tests/unit/`（秒级，必跑） |
| 改完任何后端代码提交前 | `pytest tests/unit/`（119 用例 ~9s） |
| 改了生成链路 / prompt / 解码参数 | `test_full_chain.py`（必跑，看质量指标） |
| 改了检索（向量/关键词/RRF/rerank/实体图） | `test_retrieval_chain.py`（看 context 事件注入了什么） |
| 改了按需加载（LOAD_REFS/LOAD_SETTING/目录/两阶段） | `test_on_demand_load.py`（看 refs 事件与答案是否真来自资料） |
| 改了上下文引擎 / 摄取 / 记忆 / SKILL 调度 | `probe_pipeline.py`（快速回归，不花钱） |
| 改了路由装配 / 启动流程 / 建表 | `smoke_startup.py` |

## 起临时后端跑 e2e（不动你正在用的 8000）

`dev.py` 支持 `PORT`：改代码后用另一个端口起新实例，跑完即杀，避免打断手头的后端。

```bash
cd E:/AI小说创作/backend
PORT=8010 DEV_RELOAD=0 CODEBUDDY_SAFE_DELETE_ENABLED=0 <venv>/python.exe dev.py   # 后台起
<venv>/python.exe tests/e2e/test_retrieval_chain.py --base-url http://127.0.0.1:8010
```

⚠️ `DEV_RELOAD` 必须为 0（沙箱里 reload 的孙进程关不掉，见 04-A1）。
