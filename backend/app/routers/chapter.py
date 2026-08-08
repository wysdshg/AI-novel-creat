"""模块2/3：章节生成控制器 + 剧情商讨缓存（需求 2、3、6）。

generate 接口：若已配置默认模型，则经 gateway 适配器流式生成真实正文（SSE chunk 事件），
失败或无可用的模型时优雅降级为占位文本，保证前端流程不中断。生成完成后落库 chapters。
"""
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.schemas.chapter import GenerateRequest, ChapterCreate, ChapterUpdate
from app.core.response import ok
from app.core.database import get_session
from app.services import stubs, chapter_crud, model_crud
from app.core.gateway.registry import get_adapter

router = APIRouter(tags=["章节生成"])


def _build_messages(body: GenerateRequest) -> list[dict]:
    """组装模型 Prompt：系统设定 + 用户本章要求。"""
    sys = (
        "你是一名专业的小说创作助手，擅长中文网络小说写作。"
        "请严格按照用户给出的结构化要素创作本章，保持人物性格与世界观一致，"
        "文风流畅、有画面感，禁止出现 AI 套话与说教。\n"
        "【输出格式硬性要求——务必严格遵守】\n"
        "1. 只输出本章正文本身，且必须全部使用中文（含标点）。\n"
        "2. 严禁输出任何英文（包括 Planning / Revised Plan / Actually / Let's 等），"
        "严禁复述本系统指令，严禁展示你的思考、规划或推理过程，"
        "不要写‘好的’‘本章如下’之类的开场白。\n"
        "3. 不要使用 Markdown 代码块、标题符号或大纲式罗列，直接以连贯的小说段落行文。\n"
        "4. 一旦发现自己写出了英文或规划性语句，立即丢弃并只保留中文正文。"
    )
    parts = [f"请创作第 {body.chapter_no} 章。"]
    if body.prompt_hint:
        parts.append(f"本章要点：{body.prompt_hint}")
    wr = body.word_range or {"min": 3000, "max": 5000}
    parts.append(f"目标字数约 {wr.get('min', 3000)}~{wr.get('max', 5000)} 字。")
    if body.trigger_foreshadow_ids:
        parts.append(f"本章程需呼应伏笔：{', '.join(body.trigger_foreshadow_ids)}")
    user = "\n".join(parts)
    return [
        {"role": "system", "content": sys},
        {"role": "user", "content": user},
    ]


@router.post("/projects/{project_id}/chapters/generate")
def generate_chapter(project_id: str, body: GenerateRequest, db: Session = Depends(get_session)):
    """单章生成（流式 SSE）。"""
    chapter_no = body.chapter_no
    messages = _build_messages(body)

    default = model_crud.get_default(db)
    use_model = default is not None and (default.status or "active") == "active"

    def event_stream():
        yield f"event: start\ndata: {json.dumps({'chapter_no': chapter_no}, ensure_ascii=False)}\n\n"
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
            try:
                adapter = get_adapter(default.vendor, config)
                for delta in adapter.stream(messages, temperature=body.temperature):
                    content_parts.append(delta)
                    yield f"event: chunk\ndata: {json.dumps({'text': delta}, ensure_ascii=False)}\n\n"
            except Exception as e:  # noqa: BLE001
                content_parts.append(f"\n[模型调用失败，已降级为占位：{str(e)[:200]}]")
                yield f"event: chunk\ndata: {json.dumps({'text': content_parts[-1]}, ensure_ascii=False)}\n\n"
        else:
            placeholder = "[章节正文占位 — 未配置可用模型，请在「模型配置」中添加并设为默认]"
            content_parts.append(placeholder)
            yield f"event: chunk\ndata: {json.dumps({'text': placeholder}, ensure_ascii=False)}\n\n"

        full = "".join(content_parts)
        yield f"event: validate\ndata: {json.dumps({'issues': []}, ensure_ascii=False)}\n\n"

        # 落库
        chapter = chapter_crud.create_chapter(
            db,
            project_id,
            ChapterCreate(
                chapter_no=chapter_no,
                title=f"第{chapter_no}章",
                content=full,
                word_count=len(full),
            ),
        )
        yield f"event: done\ndata: {json.dumps({'chapter_id': chapter.id, 'word_count': chapter.word_count}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/projects/{project_id}/chapters")
def create_chapter(project_id: str, body: ChapterCreate, db: Session = Depends(get_session)):
    chapter = chapter_crud.create_chapter(db, project_id, body)
    return ok({"id": chapter.id, **body.model_dump()})


@router.get("/projects/{project_id}/chapters")
def list_chapters(project_id: str, db: Session = Depends(get_session)):
    # TODO: 从 chapters 表查询并分页；当前回退到桩以保证兼容
    return ok(stubs.list_chapters(project_id))


@router.get("/projects/{project_id}/chapters/{chapter_id}")
def get_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_session)):
    o = chapter_crud.get_chapter(db, project_id, chapter_id)
    if not o:
        return ok({"id": chapter_id, "content": "", "note": ""})
    return ok({
        "id": o.id,
        "chapter_no": o.chapter_no,
        "title": o.title,
        "content": o.content,
        "note": o.note,
        "word_count": o.word_count,
    })


@router.put("/projects/{project_id}/chapters/{chapter_id}")
def update_chapter(project_id: str, chapter_id: str, body: ChapterUpdate):
    return ok({"id": chapter_id, **body.model_dump(exclude_unset=True)})


@router.delete("/projects/{project_id}/chapters/{chapter_id}")
def delete_chapter(project_id: str, chapter_id: str):
    return ok({"deleted": chapter_id})
