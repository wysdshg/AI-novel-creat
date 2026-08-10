"""模块5：章节记忆与阶段压缩（需求 4、8）。

原来这里是三个返回假数据的桩。现在接真表：
- 章级记忆 chapter_memories：每章一条，写后摄取自动生成，也可手动重跑
- 阶段摘要 stage_summaries：每 N 章压一条，防止上下文线性膨胀
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.models.orm import ChapterORM
from app.services import ingestion, memory_crud

router = APIRouter(tags=["记忆压缩"])


@router.post("/projects/{project_id}/memory/ingest/{chapter_id}")
def ingest_chapter(project_id: str, chapter_id: str, db: Session = Depends(get_session)):
    """对指定章节重跑写后摄取（抽记忆 + 写摘要 + 推走向）。

    用途：自动摄取失败、或作者手改正文后想刷新记忆。
    """
    chapter = db.query(ChapterORM).filter_by(id=chapter_id, project_id=project_id).first()
    if chapter is None:
        raise HTTPException(status_code=404, detail="章节不存在")
    return ok(ingestion.ingest_chapter(db, project_id, chapter))


@router.get("/projects/{project_id}/memory/chapters")
def list_memories(project_id: str, article_id: str | None = None,
                  db: Session = Depends(get_session)):
    rows = memory_crud.list_chapter_memories(db, project_id, article_id)
    return ok([memory_crud.memory_to_dict(r) for r in rows])


@router.get("/projects/{project_id}/memory/chapters/{chapter_id}")
def get_memory(project_id: str, chapter_id: str, db: Session = Depends(get_session)):
    o = memory_crud.get_chapter_memory(db, project_id, chapter_id)
    if not o:
        return ok(None)
    return ok(memory_crud.memory_to_dict(o))


@router.delete("/projects/{project_id}/memory/chapters/{chapter_id}")
def delete_memory(project_id: str, chapter_id: str, db: Session = Depends(get_session)):
    return ok({"deleted": memory_crud.delete_chapter_memory(db, project_id, chapter_id)})


@router.post("/projects/{project_id}/memory/compress")
def compress_memory(project_id: str, from_no: int, to_no: int,
                    db: Session = Depends(get_session)):
    """手动压缩指定章号区间为一条阶段摘要。"""
    if to_no < from_no:
        raise HTTPException(status_code=400, detail="结束章号不能小于起始章号")
    r = ingestion.compress_stage(db, project_id, from_no, to_no)
    if r is None:
        raise HTTPException(status_code=400, detail="该区间没有可用的章级记忆，请先摄取")
    return ok(r)


@router.get("/projects/{project_id}/memory/stages")
def list_stages(project_id: str, db: Session = Depends(get_session)):
    rows = memory_crud.list_stage_summaries(db, project_id)
    return ok([memory_crud.stage_to_dict(r) for r in rows])


@router.get("/projects/{project_id}/memory/summary")
def get_memory_summary(project_id: str, db: Session = Depends(get_session)):
    """记忆总览：阶段脉络 + 最近 5 章明细。前端「记忆」面板用。"""
    stages = memory_crud.list_stage_summaries(db, project_id)
    recent = memory_crud.list_chapter_memories(db, project_id, limit=5)
    return ok({
        "stages": [memory_crud.stage_to_dict(s) for s in stages],
        "recent": [memory_crud.memory_to_dict(m) for m in recent],
        "chapter_memory_count": len(memory_crud.list_chapter_memories(db, project_id)),
    })


@router.get("/projects/{project_id}/memory/events")
def list_major_events(project_id: str, db: Session = Depends(get_session)):
    """全书大事记：把各章的 plot_points 按章号铺开。"""
    rows = memory_crud.list_chapter_memories(db, project_id)
    rows.sort(key=lambda r: r.chapter_no)
    events = []
    for r in rows:
        for p in (r.plot_points or []):
            events.append({"chapter_no": r.chapter_no, "title": r.title, "event": str(p)})
    return ok(events)


@router.get("/projects/{project_id}/memory/pending-entities")
def list_pending_entities(project_id: str, db: Session = Depends(get_session)):
    """待确认入库的新实体（需求 1：AI 写数据库，但先经作者过目）。"""
    rows = memory_crud.list_chapter_memories(db, project_id)
    out = []
    for r in rows:
        if r.status != "pending":
            continue
        for e in (r.new_entities or []):
            out.append({
                "chapter_id": r.chapter_id,
                "chapter_no": r.chapter_no,
                "kind": e.get("kind"),
                "name": e.get("name"),
                "brief": e.get("brief"),
            })
    return ok(out)
