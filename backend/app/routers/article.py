"""篇（article）路由：4 级结构 小说→卷→篇→章 ——「篇」层 API。

- GET  /projects/{pid}/articles     列出本书所有篇（按卷过滤可选）
- POST /projects/{pid}/volumes/{vid}/articles  在指定卷下新建篇
- GET  /projects/{pid}/articles/{aid}  篇详情
- PUT  /projects/{pid}/articles/{aid}  篇更新（允许换卷）
- DELETE /projects/{pid}/articles/{aid}  删除篇
- GET  /articles/{aid}/chapters     列出该篇下的章
- POST /articles/{aid}/chapters     在该篇下新建章
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.response import ok
from app.schemas.article import ArticleCreate, ArticleUpdate
from app.schemas.chapter import ChapterCreate
from app.services import article_crud, chapter_crud

router = APIRouter(tags=["篇（article）"])


def _to_article_dict(o):
    return {
        "id": o.id,
        "volume_id": o.volume_id,
        "project_id": o.project_id,
        "name": o.name,
        "summary": o.summary,
        "sort_order": o.sort_order,
        "created_at": o.created_at,
        "updated_at": o.updated_at,
    }


def _to_chapter_dict(o):
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


@router.get("/projects/{project_id}/articles")
def list_articles(project_id: str, volume_id: str | None = None, db: Session = Depends(get_session)):
    return ok([_to_article_dict(a) for a in article_crud.list_articles(db, project_id, volume_id)])


@router.post("/projects/{project_id}/volumes/{volume_id}/articles")
def create_article(project_id: str, volume_id: str, body: ArticleCreate, db: Session = Depends(get_session)):
    # 强制把 volume_id 设为 URL 里的，保证不会跨卷创建
    o = article_crud.create_article(db, project_id, body.model_copy(update={"volume_id": volume_id}))
    if not o:
        return ok({"created": False, "reason": "volume_not_found"})
    return ok(_to_article_dict(o))


@router.get("/projects/{project_id}/articles/{article_id}")
def get_article(project_id: str, article_id: str, db: Session = Depends(get_session)):
    o = article_crud.get_article(db, project_id, article_id)
    if not o:
        return ok(None)
    return ok(_to_article_dict(o))


@router.put("/projects/{project_id}/articles/{article_id}")
def update_article(project_id: str, article_id: str, body: ArticleUpdate, db: Session = Depends(get_session)):
    o = article_crud.update_article(db, project_id, article_id, body)
    if not o:
        return ok({"updated": False, "id": article_id})
    return ok(_to_article_dict(o))


@router.delete("/projects/{project_id}/articles/{article_id}")
def delete_article(project_id: str, article_id: str, db: Session = Depends(get_session)):
    ok_flag = article_crud.delete_article(db, project_id, article_id)
    return ok({"deleted": article_id, "ok": ok_flag})


# —— 篇下挂章 ——
@router.get("/articles/{article_id}/chapters")
def list_chapters_by_article(article_id: str, db: Session = Depends(get_session)):
    """按篇列章：通过 article_id 找到篇，回退到按篇列章。"""
    from app.models.orm import ArticleORM
    art = db.query(ArticleORM).filter_by(id=article_id).first()
    if not art:
        return ok([])
    return ok([_to_chapter_dict(c) for c in chapter_crud.list_chapters(db, art.project_id, article_id=article_id)])


@router.post("/articles/{article_id}/chapters")
def create_chapter_under_article(article_id: str, body: ChapterCreate, db: Session = Depends(get_session)):
    """在指定篇下新建章。"""
    from app.models.orm import ArticleORM
    art = db.query(ArticleORM).filter_by(id=article_id).first()
    if not art:
        return ok({"created": False, "reason": "article_not_found"})
    # 强制把 article_id 设为 URL 里的
    o = chapter_crud.create_chapter(db, art.project_id, body.model_copy(update={"article_id": article_id}))
    return ok(_to_chapter_dict(o))
