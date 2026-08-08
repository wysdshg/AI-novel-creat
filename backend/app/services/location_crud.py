"""地点库 CRUD 服务（模块1：分作品资料库）。

分作品隔离通过 project_id 实现：所有查询/写入均按 project_id 过滤。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.orm import LocationORM
from app.schemas.database import Location, LocationCreate, LocationUpdate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_schema(o: LocationORM) -> Location:
    return Location(
        id=o.id,
        name=o.name,
        location_type=o.location_type,
        region=o.region,
        description=o.description,
        notable_features=o.notable_features or [],
        related_ids=o.related_ids or [],
        plane=o.plane,
        center_x=o.center_x,
        center_y=o.center_y,
        shape=o.shape,
        radius=o.radius,
        radius_y=o.radius_y,
        angle=o.angle,
        angle_span=o.angle_span,
        height=o.height,
        polygon=o.polygon,
    )


def list_locations(db: Session, project_id: str) -> list[Location]:
    rows = (
        db.query(LocationORM)
        .filter_by(project_id=project_id)
        .order_by(LocationORM.name)
        .all()
    )
    return [_to_schema(r) for r in rows]


def create_location(db: Session, project_id: str, data: LocationCreate) -> Location:
    now = _now()
    o = LocationORM(
        id=uuid.uuid4().hex,
        project_id=project_id,
        name=data.name,
        location_type=data.location_type,
        region=data.region,
        description=data.description,
        notable_features=data.notable_features or [],
        related_ids=data.related_ids or [],
        plane=data.plane,
        center_x=data.center_x,
        center_y=data.center_y,
        shape=data.shape,
        radius=data.radius,
        radius_y=data.radius_y,
        angle=data.angle,
        angle_span=data.angle_span,
        height=data.height,
        polygon=data.polygon,
        created_at=now,
        updated_at=now,
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return _to_schema(o)


# 8 方位文本：x 向东为正，y 向北为正，0°=北，顺时针
def _bearing_text(dx: float, dy: float) -> str:
    import math
    a = math.degrees(math.atan2(dx, dy))  # -180~180
    dirs = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    idx = round(((a + 360) % 360) / 45) % 8
    return dirs[idx]


def geo_relations(db: Session, project_id: str, location_id: str):
    """返回与指定地点同位面、且双方均有坐标的其他地点及其方位/距离。"""
    target = get_location(db, project_id, location_id)
    if target is None:
        return None
    if target.center_x is None or target.center_y is None:
        return {"plane": target.plane, "origin": {"id": target.id, "name": target.name},
                "relations": []}
    rows = list_locations(db, project_id)
    relations = []
    for r in rows:
        if r.id == target.id:
            continue
        if (r.plane or None) != (target.plane or None):
            continue
        if r.center_x is None or r.center_y is None:
            continue
        dx = r.center_x - target.center_x
        dy = r.center_y - target.center_y
        dist = (dx * dx + dy * dy) ** 0.5
        relations.append({
            "id": r.id,
            "name": r.name,
            "bearing": _bearing_text(dx, dy),
            "distance": round(dist, 4),
            "height_diff": (r.height - target.height) if (r.height is not None and target.height is not None) else None,
        })
    return {"plane": target.plane, "origin": {"id": target.id, "name": target.name},
            "relations": relations}


def get_location(db: Session, project_id: str, location_id: str):
    return (
        db.query(LocationORM)
        .filter_by(project_id=project_id, id=location_id)
        .first()
    )


def update_location(
    db: Session, project_id: str, location_id: str, data: LocationUpdate
) -> Location | None:
    o = get_location(db, project_id, location_id)
    if o is None:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(o, field, value)
    o.updated_at = _now()
    db.commit()
    db.refresh(o)
    return _to_schema(o)


def delete_location(db: Session, project_id: str, location_id: str) -> bool:
    o = get_location(db, project_id, location_id)
    if o is None:
        return False
    db.delete(o)
    db.commit()
    return True
