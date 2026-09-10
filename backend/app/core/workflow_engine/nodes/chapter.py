"""章节生成节点（本项目专属）：整章生成并落库。

复用与 generate_chapter 相同的已验证链路：
- 上下文引擎 build_chapter_messages（角色/设定/伏笔/记忆/参考文档/SKILL）
- 防复读解码参数（ModelScope Qwen3.5 惩罚归零等，见 common.py）
- 尾部重复段落裁剪 + 落库（chapter_crud）

差异说明：generate_chapter 走 SSE 流式 + 写后摄取（记忆/摘要/走向建议）；
本节点为引擎内同步调用，正文落库后直接返回，写后摄取留待后续接入
（工作流侧可用「代码节点」或二期迭代节点替代）。
"""
import logging
from ..base import BaseNode, NodeResult


logger = logging.getLogger(__name__)


class ChapterNode(BaseNode):
    node_type = "chapter"
    node_label = "章节生成"
    category = "小说创作"
    description = "整章生成并落库：复用上下文引擎（角色/设定/记忆/参考文档）+ 防复读解码参数，输出 chapter_id 与正文。"
    params_schema = [
        {"name": "project_id", "label": "小说(project_id)", "type": "variable", "required": True,
         "placeholder": "如 start.project_id"},
        {"name": "article_id", "label": "篇(article_id)", "type": "variable", "required": True,
         "placeholder": "如 start.article_id"},
        {"name": "chapter_no", "label": "章节号", "type": "number", "required": False,
         "help": "留空 = 自动取本篇最大序号 +1"},
        {"name": "prompt_hint", "label": "本章要点", "type": "textarea", "required": False,
         "help": "支持 {{#node.var#}} 引用（如把上一节点输出拼进来）"},
        {"name": "title", "label": "章节标题", "type": "string", "required": False,
         "placeholder": "留空 = 第N章"},
        {"name": "word_range_min", "label": "目标字数(最小)", "type": "number", "default": 3000},
        {"name": "word_range_max", "label": "目标字数(最大)", "type": "number", "default": 5000},
        {"name": "model_id", "label": "模型", "type": "string", "required": False,
         "placeholder": "留空 = 使用默认模型"},
        {"name": "temperature", "label": "温度", "type": "number", "default": 0.75},
        {"name": "enable_thinking", "label": "开启思考", "type": "boolean", "required": False,
         "help": "留空 = 跟随模型配置"},
    ]
    outputs_desc = {
        "chapter_id": "落库章节 id",
        "chapter_no": "章节号",
        "word_count": "正文字数",
        "content": "正文全文（可能很长）",
    }

    def _run(self, pool, db, inputs: dict) -> NodeResult:
        from app.core.context import build_chapter_messages
        from app.core.gateway.registry import get_adapter
        from app.models.orm import ArticleORM, ModelConfigORM
        from app.schemas.chapter import ChapterCreate
        from app.services import chapter_crud
        from app.services.model_crud import get_default

        from ..common import build_llm_config, chapter_max_tokens, dedup_trailing_repeats

        project_id = str(pool.resolve_value(self.params.get("project_id")) or "")
        article_id = str(pool.resolve_value(self.params.get("article_id")) or "")
        if not project_id or not article_id:
            return NodeResult(status="failed", error="缺少 project_id / article_id（请用变量引用 start 节点输入）")

        art = db.query(ArticleORM).filter_by(id=article_id, project_id=project_id).first()
        if art is None:
            return NodeResult(status="failed", error=f"篇 {article_id} 不存在（project_id/article_id 是否对得上？）")
        volume_id = getattr(art, "volume_id", None)

        # 章节号：指定 or 自动取本篇最大 +1
        raw_no = self.params.get("chapter_no")
        if raw_no is None or str(raw_no).strip() == "":
            existing = chapter_crud.list_chapters(db, project_id, article_id=article_id)
            chapter_no = max([c.chapter_no for c in existing], default=0) + 1
        else:
            try:
                chapter_no = int(raw_no)
            except (TypeError, ValueError):
                return NodeResult(status="failed", error=f"章节号非法: {raw_no}")

        hint = pool.render(self.params.get("prompt_hint") or "")
        title = pool.render(self.params.get("title") or "") or None
        try:
            wmin = int(self.params.get("word_range_min") or 3000)
            wmax = int(self.params.get("word_range_max") or 5000)
        except (TypeError, ValueError):
            wmin, wmax = 3000, 5000
        if wmin <= 0 or wmax < wmin:
            wmin, wmax = 3000, 5000
        word_range = {"min": wmin, "max": wmax}

        # 上下文组装（工作流场景无对话线程 → from_discussion=False）
        try:
            messages, _ctx_meta = build_chapter_messages(
                db, project_id,
                chapter_no=chapter_no,
                article_id=article_id,
                volume_id=volume_id,
                prompt_hint=hint,
                word_range=word_range,
                from_discussion=False,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[workflow/chapter_node] 上下文组装失败，降级: {type(e).__name__}: {e}")
            messages = [
                {"role": "system", "content": "你是中文网络小说代笔，只输出本章正文，全中文。"},
                {"role": "user", "content": f"创作第 {chapter_no} 章。要点：{hint or '自行推进剧情'}"},
            ]

        # 模型
        model_id = (self.params.get("model_id") or "").strip() or None
        model_orm = db.query(ModelConfigORM).filter_by(id=model_id).first() if model_id else get_default(db)
        if model_orm is None or (model_orm.status or "active") != "active":
            return NodeResult(status="failed", error="未配置可用模型（请在「模型配置」中添加并设为默认）")

        model_cfg = {
            "vendor": model_orm.vendor,
            "api_base": model_orm.api_base,
            "api_key": model_orm.api_key,
            "model_name": model_orm.model_name,
            "temperature": model_orm.temperature,
            "top_p": model_orm.top_p,
            "max_tokens": model_orm.max_tokens,
            "enable_thinking": model_orm.enable_thinking,
        }
        try:
            temperature = float(self.params.get("temperature") if self.params.get("temperature") is not None else 0.75)
        except (TypeError, ValueError):
            temperature = 0.75
        max_tokens = chapter_max_tokens(wmax)
        config = build_llm_config(
            model_cfg,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_thinking=self.params.get("enable_thinking"),
        )
        adapter = get_adapter(model_orm.vendor, config)

        # 同步生成全文（引擎内非流式；SSE 按节点粒度上报进度）
        try:
            full = adapter.chat(
                messages,
                temperature=temperature,
                enable_thinking=config.get("enable_thinking"),
                max_tokens=max_tokens,
            ) or ""
        except Exception as e:  # noqa: BLE001
            return NodeResult(status="failed", error=f"模型调用失败: {type(e).__name__}: {str(e)[:200]}")

        # 后处理：尾部重复段落去重
        if len(full) > 200:
            cleaned = dedup_trailing_repeats(full)
            if len(cleaned) < len(full):
                logger.info(f"[workflow/chapter_node] 后处理去重：裁掉 {len(full) - len(cleaned)} 字符")
                full = cleaned

        if not full.strip():
            return NodeResult(status="failed", error="模型返回空正文")

        # 落库
        chapter = chapter_crud.create_chapter(
            db, project_id,
            ChapterCreate(
                chapter_no=chapter_no,
                title=title or f"第{chapter_no}章",
                content=full,
                word_count=len(full),
                article_id=article_id,
            ),
        )
        return NodeResult(outputs={
            "chapter_id": chapter.id,
            "chapter_no": chapter.chapter_no,
            "word_count": chapter.word_count,
            "content": full,
        })
