"""作品（项目）真实 CRUD（§1 分作品隔离）。

- 新建作品：生成 uuid 主键，落库 projects 表；
- 列表：分页返回，附 chapter_count（已写章节数）；
- 详情 / 修改 / 删除（级联清空该作品下所有业务数据）。
所有操作按 project_id 隔离，保证不同小说数据互不干扰。
"""
import uuid
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.orm import (
    ProjectORM, CharacterORM, SkillORM, RelationORM, FactionORM,
    ForeshadowORM, ChapterORM, DiscussionMessageORM, DirectionORM, OutlineORM,
)


def _to_dict(orm: ProjectORM, chapter_count: int = 0) -> dict:
    return {
        "id": orm.id,
        "name": orm.name,
        "genre": orm.genre,
        "summary": orm.summary,
        "status": orm.status,
        "db_backend": orm.db_backend,
        "created_at": orm.created_at,
        "updated_at": orm.updated_at,
        "chapter_count": chapter_count,
    }


def _count_chapters(db: Session, project_id: str) -> int:
    return db.scalar(
        select(func.count()).select_from(ChapterORM).where(ChapterORM.project_id == project_id)
    ) or 0


def create_project(db: Session, data: dict) -> dict:
    orm = ProjectORM(
        id=str(uuid.uuid4()),
        name=data["name"],
        genre=data.get("genre"),
        summary=data.get("summary"),
        status=data.get("status", "draft"),
        db_backend=data.get("db_backend", "sqlite"),
    )
    db.add(orm)
    db.commit()
    db.refresh(orm)
    return _to_dict(orm, chapter_count=0)


def list_projects(db: Session, page: int = 1, page_size: int = 20) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(ProjectORM)) or 0
    stmt = select(ProjectORM).order_by(ProjectORM.created_at.desc()).limit(page_size).offset((page - 1) * page_size)
    rows = db.scalars(stmt).all()
    items = [
        _to_dict(r, chapter_count=_count_chapters(db, r.id)) for r in rows
    ]
    return items, total


def get_project(db: Session, project_id: str) -> dict | None:
    orm = db.get(ProjectORM, project_id)
    if orm is None:
        return None
    return _to_dict(orm, chapter_count=_count_chapters(db, project_id))


def update_project(db: Session, project_id: str, data: dict) -> dict | None:
    orm = db.get(ProjectORM, project_id)
    if orm is None:
        return None
    for k, v in data.items():
        if v is not None and hasattr(orm, k):
            setattr(orm, k, v)
    db.commit()
    db.refresh(orm)
    return _to_dict(orm, chapter_count=_count_chapters(db, project_id))


# 删除作品时一并清空的关联表（按 project_id 过滤，互不影响其他作品）
_RELATED = [
    CharacterORM, SkillORM, RelationORM, FactionORM,
    ForeshadowORM, ChapterORM, DiscussionMessageORM, DirectionORM, OutlineORM,
]


def delete_project(db: Session, project_id: str) -> bool:
    orm = db.get(ProjectORM, project_id)
    if orm is None:
        return False
    for table in _RELATED:
        db.query(table).filter(table.project_id == project_id).delete()
    db.delete(orm)
    db.commit()
    return True
