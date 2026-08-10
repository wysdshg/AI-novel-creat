"""模块2/3：章节生成控制器 + 剧情商讨缓存（需求 2、3、6）。

generate 接口：若已配置默认模型，则经 gateway 适配器流式生成真实正文（SSE chunk 事件），
失败或无可用的模型时优雅降级为占位文本，保证前端流程不中断。生成完成后落库 chapters。
4 级结构下：chapters 必隶属 article_id；列出时按 article 过滤。

SSE 事件序列：
  start → context（这次读了哪些资料）→ chunk* → validate（AI 味检测）
  → saved（章节已落库）→ ingest（记忆抽取 + 走向建议）→ done
"""
import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.schemas.chapter import GenerateRequest, ChapterCreate, ChapterUpdate
from app.core.response import ok
from app.core.database import get_session
from app.core.context import build_chapter_messages
from app.services import (
    app_config, article_crud, chapter_crud, humanizer, ingestion, model_crud,
    reference_crud,
)
from app.core.gateway.registry import get_adapter
from app.models.orm import ReferenceDocORM

router = APIRouter(tags=["章节生成"])


# ──────────────────────────────────────────────
# 重复循环检测器（防小模型长文本复读）
# ──────────────────────────────────────────────
class _RepetitionGuard:
    """流式重复循环检测。

    小模型（8B 及以下）生成长文时容易进入「段落级死循环」——同一段落反复出现 3~5 遍。
    本守护在流式输出过程中实时监控，当检测到新内容与近期内容高度重叠时：
    - 停止向下游 yield 新 chunk（前端不再显示重复内容）
    - 标记 full 文本需要后处理去重

    算法：
      1. 维护滑动窗口（最近 _WINDOW_SIZE 字符）。
      2. 每次追加新 chunk 后，用最长公共子串检查重叠率。
      3. 重叠率 > _THRESHOLD 且重叠长度 > _MIN_OVERLAP_LEN 时判定为循环。
      4. 触发后停止 yield，但继续消费迭代器直到模型 done（避免连接泄漏）。
    """

    _WINDOW_SIZE = 600       # 滑动窗口大小（字符）
    _THRESHOLD = 0.55        # 重叠率阈值
    _MIN_OVERLAP_LEN = 40     # 最小重叠长度（短巧合不算）

    def __init__(self):
        self._buf = ""               # 已累积的全部正文
        self._triggered = False      # 是否已触发循环截断
        self._stop_yield_after = ""  # 触发后仍允许输出的尾部（收束当前句子）

    def feed(self, chunk: str) -> bool:
        """传入新 chunk，返回是否应该继续 yield 给下游。

        返回 True = 正常，可以 yield；
        返回 False = 检测到循环，不应再 yield 新内容。
        """
        if self._triggered:
            return False

        if not chunk:
            return True

        self._buf += chunk
        # 只在累积超过窗口大小时才检测（太短时误判率高）
        if len(self._buf) < self._WINDOW_SIZE:
            return True

        # 取最近窗口 + 当前新增部分做重叠检测
        recent = self._buf[-self._WINDOW_SIZE:]
        overlap_len = self._longest_overlap(recent)
        if overlap_len >= self._MIN_OVERLAP_LEN:
            overlap_ratio = overlap_len / len(chunk) if chunk else 0
            if overlap_ratio >= self._THRESHOLD:
                self._triggered = True
                # 允许当前 chunk 的前半部分通过（收束句子），后半截断
                self._stop_yield_after = chunk[:max(1, len(chunk) // 3)]
                return False

        return True

    @staticmethod
    def _longest_overlap(text: str) -> int:
        """计算 text 后缀与 text 前缀的最长公共子串长度。

        用于检测「刚生成的内容」是否与「不久前生成的内容」高度相似。
        简化实现：从短到长枚举后缀/前缀匹配。
        """
        n = len(text)
        best = 0
        # 只检查后 1/3 与前 2/3 的重叠（减少计算量）
        split = n * 2 // 3
        suffix = text[split:]
        prefix = text[:split]
        for length in range(min(len(suffix), len(prefix)), 0, -1):
            if suffix[-length:] == prefix[:length]:
                best = length
                break
        return best

    @property
    def full_text(self) -> str:
        return self._buf

    @property
    def is_triggered(self) -> bool:
        return self._triggered


def _dedup_trailing_repeats(text: str) -> str:
    """后处理：剪掉尾部重复段落（流式检测的兜底）。

    按「\\n\\n」分段，从末尾向前检查是否有段落与前面某段高度相似（>80%），
    连续 2 段以上重复则全部裁掉。
    """
    paras = re.split(r'\n\n+', text.strip())
    if len(paras) < 3:
        return text

    kept = list(paras)
    # 从倒数第 2 段开始往前检查
    i = len(kept) - 2
    while i >= 0:
        current = kept[i].strip()
        if not current:
            i -= 1
            continue
        # 在已保留的段落中找相似的
        dup_start = -1
        for j in range(i):
            if _similarity(current, kept[j].strip()) > 0.8:
                dup_start = i
                break
        if dup_start >= 0:
            # 裁掉从 dup_start 到末尾的所有段落
            kept = kept[:dup_start]
            i = len(kept) - 2
        else:
            i -= 1

    return '\n\n'.join(kept)


def _similarity(a: str, b: str) -> float:
    """简单的字符级 Jaccard 相似度（用于段落去重判断）。"""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _maybe_load_refs(db, project_id, messages, ctx_meta, default, body) -> tuple[list, dict]:
    """hybrid 模式：在 pick_relevant 已注入的基线上，按需把最相关的全局参考拉进来。

    设计取舍（章节生成路径）：
    - 不采用「AI 两阶段 LOAD_REFS 选择」——本地 4b 模型在该协议上不稳定，
      时而全不加载、时而一股脑全加载，既加延迟又不可控；
    - 改为**确定性相关性 top-up**：复用 pick_relevant 同款 score_reference 对全局池打分，
      只注入 top-2 且分数>0 的全局资料。按需、有界、零额外延迟、可解释；
    - pick_relevant 永远是安全底线（项目内相关参考必在），本函数只补「项目没有但全局相关的」；
    - 任何异常降级为「不额外加载」，不打断生成。
    """
    try:
        baseline_ids = {d.get("id") for d in ctx_meta.get("references", [])}
        ids = _global_topup_ids(db, project_id, body.prompt_hint, baseline_ids, top_k=2)
        if not ids:
            return messages, ctx_meta

        load_ids = list(dict.fromkeys(ids))
        extra = reference_crud.fetch_refs_by_ids(db, load_ids)
        if not extra:
            return messages, ctx_meta

        extra_text = "\n\n".join(f"【参考资料（按需加载）：{fn}】\n{ct}" for fn, ct in extra)
        messages[1]["content"] += "\n\n" + extra_text
        ctx_meta = {**ctx_meta, "refs_loaded_extra": [fn for fn, _ in extra], "ref_mode": "hybrid"}
    except Exception as e:  # noqa: BLE001
        print(f"[generate_chapter] 按需参考加载失败，降级基线: {type(e).__name__}: {e}")
    return messages, ctx_meta


def _global_topup_ids(db, project_id, hint: str | None, exclude_ids: set[str], top_k: int = 2) -> list[str]:
    """确定性按需 top-up：对全局资料池按相关性打分，返回分数>0 的 top_k 个 id（排除基线）。

    章节生成 hybrid 模式的主路径（不依赖模型选择，稳定可控）：只把最相关的全局资料
    按需拉进上下文，避免把整个全局池一股脑塞爆窗口。相关性用与 pick_relevant 相同的
    score_reference，且要求分数>=4（标签/文件名真实命中），排除弱重叠噪声，保证「按需」名副其实。
    """
    try:
        from app.services.reference_crud import GLOBAL_PROJECT_ID, score_reference
        rows = (
            db.query(ReferenceDocORM)
            .filter_by(project_id=GLOBAL_PROJECT_ID)
            .filter(ReferenceDocORM.article_id.is_(None))
            .all()
        )
        scored = []
        for o in rows:
            if o.id in exclude_ids:
                continue
            s = score_reference(o, hint or "", set())
            # 阈值 >=4：只接受「标签/文件名真实命中」（score_reference 里标签×5、文件名×4），
            # 排除 2-gram 弱重叠产生的 0.x 噪声分，避免无关全局资料被误加载。
            if s >= 4:
                scored.append((s, o.id))
        scored.sort(key=lambda x: -x[0])
        return [oid for _, oid in scored[:top_k]]
    except Exception as e:  # noqa: BLE001
        print(f"[generate_chapter] 全局 top-up 失败: {e}")
        return []


@router.post("/projects/{project_id}/chapters/generate")
def generate_chapter(project_id: str, body: GenerateRequest, db: Session = Depends(get_session)):
    """单章生成（流式 SSE）。

    落库后触发写后摄取：抽章级记忆、写篇章摘要、把走向建议推到对话区。
    """
    chapter_no = body.chapter_no
    # 4 级结构约束：章节必须归属某一篇，缺失 article_id 会造成「孤儿章」
    # （不挂在任何篇下、侧栏树不显示）。前端已防呆，此处为后端兜底。
    if not body.article_id:
        raise HTTPException(
            status_code=400,
            detail="生成章节必须指定所属篇（article_id）。请先在左侧选择一篇或一章后再生成。",
        )

    # 上下文引擎：角色/设定/伏笔/记忆/商讨/参考文档/SKILL/去AI味 一次性组装
    volume_id = None
    try:
        art = article_crud.get_article(db, project_id, body.article_id)
        volume_id = getattr(art, "volume_id", None) if art else None
    except Exception:  # noqa: BLE001
        pass

    try:
        messages, ctx_meta = build_chapter_messages(
            db, project_id,
            chapter_no=chapter_no,
            article_id=body.article_id,
            volume_id=volume_id,
            prompt_hint=body.prompt_hint,
            word_range=body.word_range,
            trigger_foreshadow_ids=body.trigger_foreshadow_ids,
            from_discussion=body.from_discussion,
        )
    except Exception as e:  # noqa: BLE001
        # 上下文引擎挂了也得让作者能写字——退回最小提示词
        print(f"[generate_chapter] 上下文组装失败，降级: {type(e).__name__}: {e}")
        messages = [
            {"role": "system", "content": "你是中文网络小说代笔，只输出本章正文，全中文。"},
            {"role": "user", "content": f"创作第 {chapter_no} 章。要点：{body.prompt_hint or '自行推进剧情'}"},
        ]
        ctx_meta = {"error": str(e)[:200]}

    default = model_crud.get_default(db)
    use_model = default is not None and (default.status or "active") == "active"
    scan_enabled = bool(app_config.get(db, app_config.KEY_HUMANIZE_SCAN, True))
    ingest_enabled = bool(app_config.get(db, app_config.KEY_INGEST_ENABLED, True))

    # 按需参考加载（hybrid 模式）：在 pick_relevant 基线上让 AI 额外选装参考。
    # 默认 pick_relevant 模式不进入此分支，行为完全不变（零回归）。
    ref_mode = os.environ.get("NA_CHAPTER_REF_MODE", "pick_relevant")
    if ref_mode == "hybrid" and use_model:
        messages, ctx_meta = _maybe_load_refs(db, project_id, messages, ctx_meta, default, body)

    def event_stream():
        yield _sse("start", {"chapter_no": chapter_no})
        yield _sse("context", ctx_meta)
        if ctx_meta.get("refs_loaded_extra"):
            yield _sse("refs", {"loaded": ctx_meta["refs_loaded_extra"]})
        content_parts = []
        if use_model:
            config = {
                "api_base": default.api_base,
                "api_key": default.api_key,
                "model_name": default.model_name,
                "temperature": default.temperature,
                "top_p": default.top_p,
                "max_tokens": default.max_tokens,
                "enable_thinking": default.enable_thinking if body.enable_thinking is None else body.enable_thinking,
            }
            want_thinking = body.enable_thinking if body.enable_thinking is not None else default.enable_thinking
            try:
                adapter = get_adapter(default.vendor, config)
                guard = _RepetitionGuard()
                for delta in adapter.stream(messages, temperature=body.temperature, enable_thinking=want_thinking):
                    if guard.feed(delta):
                        content_parts.append(delta)
                        yield f"event: chunk\ndata: {json.dumps({'text': delta}, ensure_ascii=False)}\n\n"
                    else:
                        # 检测到重复循环：停止 yield，但继续消费迭代器
                        content_parts.append(delta)  # 仍记录（用于后续去重）
                        print(f"[generate_chapter] ⚠️ 检测到重复循环，停止输出（已生成 {len(guard.full_text)} 字符）")
                        # 消费完剩余 chunk（避免连接异常）
                        for _rest in adapter.stream(messages, temperature=body.temperature, enable_thinking=want_thinking):
                            content_parts.append(_rest)
                        break
            except Exception as e:  # noqa: BLE001
                content_parts.append(f"\n[模型调用失败，已降级为占位：{str(e)[:200]}]")
                yield f"event: chunk\ndata: {json.dumps({'text': content_parts[-1]}, ensure_ascii=False)}\n\n"
        else:
            placeholder = "[章节正文占位 — 未配置可用模型，请在「模型配置」中添加并设为默认]"
            content_parts.append(placeholder)
            yield f"event: chunk\ndata: {json.dumps({'text': placeholder}, ensure_ascii=False)}\n\n"

        full = "".join(content_parts)

        # 后处理：尾部重复段落去重（流式检测的兜底 + 防止漏检）
        if len(full) > 200:
            cleaned = _dedup_trailing_repeats(full)
            if len(cleaned) < len(full):
                trimmed = len(full) - len(cleaned)
                print(f"[generate_chapter] 后处理去重：裁掉 {trimmed} 字符重复内容")
                full = cleaned

        # AI 味检测：纯正则、零 token，不改写正文，只报告
        if scan_enabled and use_model:
            try:
                report = humanizer.scan(full, scene="novel")
                yield _sse("validate", report)
            except Exception as e:  # noqa: BLE001
                print(f"[generate_chapter] AI 味检测失败: {e}")
                yield _sse("validate", {"issues": []})
        else:
            yield _sse("validate", {"issues": []})

        # 落库（4 级结构下 article_id 从 body 透传）
        chapter = chapter_crud.create_chapter(
            db,
            project_id,
            ChapterCreate(
                chapter_no=chapter_no,
                title=f"第{chapter_no}章",
                content=full,
                word_count=len(full),
                article_id=body.article_id,
            ),
        )
        yield _sse("saved", {"chapter_id": chapter.id, "word_count": chapter.word_count})

        # 写后摄取：抽记忆 → 写篇章摘要 → 推走向卡片。慢一点没关系，正文已经到前端了
        if ingest_enabled and use_model:
            try:
                yield _sse("ingest_start", {"chapter_id": chapter.id})
                ing = ingestion.ingest_chapter(db, project_id, chapter)
                yield _sse("ingest", ing)
            except Exception as e:  # noqa: BLE001
                print(f"[generate_chapter] 写后摄取失败: {e}")
                yield _sse("ingest", {"error": str(e)[:200]})

        yield _sse("done", {"chapter_id": chapter.id, "word_count": chapter.word_count})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _chapter_to_dict(o):
    return {
        "id": o.id,
        "project_id": o.project_id,
        "article_id": o.article_id,
        "chapter_no": o.chapter_no,
        "title": o.title,
        "content": o.content,
        "note": o.note,
        "word_count": o.word_count,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
    }


@router.post("/projects/{project_id}/chapters")
def create_chapter(project_id: str, body: ChapterCreate, db: Session = Depends(get_session)):
    o = chapter_crud.create_chapter(db, project_id, body)
    return ok(_chapter_to_dict(o))


@router.get("/projects/{project_id}/chapters")
def list_chapters(project_id: str, article_id: str | None = None, db: Session = Depends(get_session)):
    return ok([_chapter_to_dict(c) for c in chapter_crud.list_chapters(db, project_id, article_id)])


@router.get("/projects/{project_id}/chapters/{chapter_id}")
def get_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_session)):
    o = chapter_crud.get_chapter(db, project_id, chapter_id)
    if not o:
        return ok({"id": chapter_id, "content": "", "note": ""})
    return ok(_chapter_to_dict(o))


@router.put("/projects/{project_id}/chapters/{chapter_id}")
def update_chapter(project_id: str, chapter_id: str, body: ChapterUpdate, db: Session = Depends(get_session)):
    o = chapter_crud.update_chapter(db, project_id, chapter_id, body)
    if not o:
        return ok({"updated": False, "id": chapter_id})
    return ok(_chapter_to_dict(o))


@router.delete("/projects/{project_id}/chapters/{chapter_id}")
def delete_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_session)):
    ok_flag = chapter_crud.delete_chapter(db, project_id, chapter_id)
    return ok({"deleted": chapter_id, "ok": ok_flag})
