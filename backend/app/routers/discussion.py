"""模块3：剧情商讨会话（需求 6）。

- GET    /discussion            返回当前商讨缓存（已持久化、未归档）
- POST   /discussion/messages   手动追加一条消息（闲聊、不调模型）
- DELETE /discussion            清空当前商讨缓存
- POST   /discussion/archive    将当前草稿归档为指定章节备注并移出缓存
- POST   /discussion/chat       流式调用默认模型，结束后再把「用户提问 + AI 回复」落库
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.schemas.chapter import DiscussionMessageCreate, DiscussionChatRequest
from app.core.response import ok
from app.core.database import get_session
from app.services import model_crud
from app.services.discussion_crud import (
    list_messages,
    add_message,
    clear_messages,
    archive_to_chapter,
)
from app.core.gateway.registry import get_adapter
from app.models.orm import ChapterORM

router = APIRouter(tags=["剧情商讨"])

_SYS_PROMPT = (
    "你是一名专业的小说创作助手，正在和作者讨论本章剧情走向。"
    "请基于已有的世界观与人物设定，给出具体、可操作的剧情建议，"
    "保持逻辑与人物一致，语言简洁有启发，不要替作者代写整章正文。\n"
    "【输出格式硬性要求——务必严格遵守】\n"
    "1. 只输出最终回复正文，且必须全部使用中文。\n"
    "2. 严禁输出任何英文（包括 Planning / Revised Plan / Actually / Let's 等），"
    "严禁复述本系统指令，严禁展示你的思考、规划或推理过程。\n"
    "3. 不要写 ‘好的’‘我来…’ 之类的开场白套话，直接给出建议。\n"
    "4. 一旦发现自己写出了英文或规划性语句，立即丢弃并只保留中文建议正文。"
)


def _to_frontend(m) -> dict:
    """ORM → 前端可渲染的消息结构（role 统一为 user/ai）。"""
    return {
        "id": m.id,
        "role": "ai" if m.role == "assistant" else "user",
        "content": m.content or "",
        "thinking": m.thinking or "",
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/projects/{project_id}/discussion")
def get_discussion(project_id: str, db: Session = Depends(get_session)):
    """返回当前商讨缓存（已持久化、未归档）消息列表。"""
    return ok([_to_frontend(m) for m in list_messages(db, project_id)])


@router.post("/projects/{project_id}/discussion/messages")
def append_message(
    project_id: str,
    body: DiscussionMessageCreate,
    db: Session = Depends(get_session),
):
    """手动追加一条商讨消息（闲聊、不调模型）。"""
    m = add_message(db, project_id, body.role, body.content)
    return ok(_to_frontend(m))


@router.delete("/projects/{project_id}/discussion")
def clear_discussion(project_id: str, db: Session = Depends(get_session)):
    """清空当前商讨缓存。"""
    n = clear_messages(db, project_id)
    return ok({"cleared": project_id, "count": n})


@router.post("/projects/{project_id}/discussion/archive")
def archive_discussion(
    project_id: str,
    chapter_id: str,
    db: Session = Depends(get_session),
):
    """将当前商讨草稿归档为指定章节备注，并移出当前缓存。"""
    chapter = db.query(ChapterORM).filter_by(id=chapter_id, project_id=project_id).first()
    if chapter is None:
        raise HTTPException(status_code=404, detail="章节不存在")
    result = archive_to_chapter(db, project_id, chapter_id)
    return ok(result)


@router.post("/projects/{project_id}/discussion/chat")
def chat(
    project_id: str,
    body: DiscussionChatRequest,
    db: Session = Depends(get_session),
):
    """剧情商讨：用默认模型流式回复用户（SSE）。结束后把本轮对话落库。"""
    default = model_crud.get_default(db)
    use_model = default is not None and (default.status or "active") == "active"

    # 取最近一条 user 消息，用于结束后的持久化
    last_user_content = ""
    for m in reversed(body.messages):
        if (m or {}).get("role") == "user":
            last_user_content = (m or {}).get("content", "") or ""
            break

    def event_stream():
        if not use_model:
            yield f"event: chunk\ndata: {json.dumps({'text': '[未配置可用模型，请在「模型配置」中添加并设为默认]'}, ensure_ascii=False)}\n\n"
            yield "event: done\ndata: {}\n\n"
            return

        config = {
            "api_base": default.api_base,
            "api_key": default.api_key,
            "model_name": default.model_name,
            "temperature": default.temperature,
            "top_p": default.top_p,
            "max_tokens": default.max_tokens,
            "enable_thinking": default.enable_thinking if body.enable_thinking is None else body.enable_thinking,
        }
        messages = [{"role": "system", "content": _SYS_PROMPT}]
        for m in body.messages:
            content = (m or {}).get("content", "")
            if content:
                role = (m or {}).get("role", "user")
                messages.append({"role": role, "content": content})

        want_thinking = body.enable_thinking if body.enable_thinking is not None else default.enable_thinking
        temperature = body.temperature or default.temperature

        assistant_text: list[str] = []
        assistant_thinking: list[str] = []
        try:
            adapter = get_adapter(default.vendor, config)

            # 1) 思考过程（可选）：仅 Ollama 原生适配器支持 stream_thinking
            if want_thinking and hasattr(adapter, "stream_thinking"):
                for t in adapter.stream_thinking(messages, temperature=temperature):
                    assistant_thinking.append(t)
                    yield f"event: thinking\ndata: {json.dumps({'text': t}, ensure_ascii=False)}\n\n"

            # 2) 正文/回复：始终使用 think=false 的干净内容（Ollama 原生适配器保证）
            for delta in adapter.stream(messages, temperature=temperature):
                assistant_text.append(delta)
                yield f"event: chunk\ndata: {json.dumps({'text': delta}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"event: chunk\ndata: {json.dumps({'text': f'[模型调用失败：{str(e)[:200]}]'}, ensure_ascii=False)}\n\n"
        finally:
            yield "event: done\ndata: {}\n\n"
            # 持久化本轮对话：用户提问 + AI 回复（含思考过程）
            try:
                full = "".join(assistant_text)
                if last_user_content:
                    add_message(db, project_id, "user", last_user_content)
                if full:
                    add_message(
                        db,
                        project_id,
                        "assistant",
                        full,
                        thinking="".join(assistant_thinking) or None,
                        meta={"enable_thinking": bool(want_thinking)},
                    )
            except Exception as e:  # noqa: BLE001
                print(f"[discussion/chat] 持久化失败: {e}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")
