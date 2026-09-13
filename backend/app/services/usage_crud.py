"""模型用量计量（Phase 4.2 观测消费端，2026-09-10）。

职责：记录每次模型调用的 token 用量，并提供聚合统计（按模型 / 场景 / 日期）。

设计原则：
- **计量是旁路**：任何异常都不得冒泡到模型调用主链路（同 `eval_crud`）。
- **区分真实与估算**：厂商回流 usage 时 `estimated=False`；没回流就按字符估算并标
  `estimated=True` —— 两者不能混为一谈，否则统计会假装很精确。
- **失败也记**（`ok=False`）：prompt 已经发出去，失败同样烧 token。

成本说明：本模块只统计 **token 数**，不算金额 —— 各厂商单价差异大且会变，
需要金额时按 token 量自行换算（单价可放 `app_configs`，本轮不做）。
"""
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.orm import LlmUsageLogORM

logger = logging.getLogger(__name__)

# 中文按 ~1.5 token/字 估算（与 chapter.py 的 max_tokens 公式同源）。
# 只是量级参考：厂商不回流 usage 时才用，页面上会标注"估算"。
CHARS_PER_TOKEN = 1.5


def estimate_tokens(text: str) -> int:
    """按字符数粗估 token（中文 ~1.5 token/字）。"""
    return int(len(text or "") / CHARS_PER_TOKEN)


def record_usage(db: Session, *, scene: str, vendor: str | None = None,
                 model_name: str | None = None, usage: dict | None = None,
                 project_id: str | None = None, duration_ms: int | None = None,
                 ok: bool = True, trace_id: str | None = None,
                 prompt_text: str | None = None,
                 completion_text: str | None = None) -> None:
    """记录一次模型调用。**失败静默**。

    - 传了 `usage`（适配器 `last_usage` / 网关原始响应）→ 用真实数值，`estimated` 取其自带标记；
    - 没传但给了 `prompt_text` / `completion_text` → 按字符估算，标 `estimated=True`；
    - 两者都没有 → 直接返回（不记空行，避免污染统计）。

    缓存拆分（2026-09-13）：厂商（DeepSeek）把输入 token 分成命中/未命中两档，单价差 50 倍。
    归一化三个可能来源（`cache_hit_tokens` / `prompt_cache_hit_tokens` / `prompt_tokens_details.cached_tokens`），
    同时兼容 DeepSeek 特有的 `prompt_cache_miss_tokens`。
    """
    try:
        hit = miss = 0
        if isinstance(usage, dict) and (
            usage.get("prompt_tokens") is not None or usage.get("completion_tokens") is not None
        ):
            p = int(usage.get("prompt_tokens") or 0)
            c = int(usage.get("completion_tokens") or 0)
            total = int(usage.get("total_tokens") or (p + c))
            est = bool(usage.get("estimated"))
            hit, miss = _extract_cache(usage, p)
        elif prompt_text is not None or completion_text is not None:
            p = estimate_tokens(prompt_text or "")
            c = estimate_tokens(completion_text or "")
            total = p + c
            est = True
        else:
            return

        db.add(LlmUsageLogORM(
            id=uuid.uuid4().hex,
            project_id=project_id,
            scene=scene,
            vendor=vendor,
            model_name=model_name,
            prompt_tokens=p,
            completion_tokens=c,
            total_tokens=total,
            cache_hit_tokens=hit,
            cache_miss_tokens=miss,
            estimated=est,
            ok=ok,
            duration_ms=duration_ms,
            trace_id=trace_id,
            created_at=datetime.utcnow(),
        ))
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[usage] 用量记录失败（不影响调用）scene={scene}: {type(e).__name__}: {e}")
        try:
            db.rollback()
        except Exception as e2:  # noqa: BLE001
            logger.debug(f"[usage] rollback 失败: {type(e2).__name__}: {e2}")


def _extract_cache(usage: dict, prompt_total: int) -> tuple[int, int]:
    """从厂商 usage 里抽出（命中缓存, 未命中缓存）两档输入 token。

    兼容三种厂商命名（2026-09-13 实测确认 DeepSeek 走第二种）：
    1. 通用：`cache_hit_tokens` / `cache_miss_tokens`
    2. DeepSeek：`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`
    3. OpenAI 系：`prompt_tokens_details.cached_tokens`（只给命中，未命中需反算）

    **未知归一为 (0, 0) 而不是 (0, prompt_total)** —— 后者会把"厂商没回传缓存信息"
    伪装成"全部未命中"，把统计打成一片红，反而误导优化方向。
    """
    def _i(v):
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0

    hit = _i(usage.get("cache_hit_tokens") or usage.get("prompt_cache_hit_tokens"))
    if not hit:
        det = usage.get("prompt_tokens_details")
        if isinstance(det, dict):
            hit = _i(det.get("cached_tokens"))
    miss = _i(usage.get("cache_miss_tokens") or usage.get("prompt_cache_miss_tokens"))
    if not miss and hit:
        miss = max(0, prompt_total - hit)
    if not hit and not miss:
        return 0, 0
    return hit, miss


def _bucket(rows: list[LlmUsageLogORM]) -> dict:
    """把一组日志聚合出 calls / tokens / 缓存命中率 / estimated 比例。"""
    calls = len(rows)
    tokens = sum(r.total_tokens or 0 for r in rows)
    est_calls = sum(1 for r in rows if r.estimated)
    failed = sum(1 for r in rows if not r.ok)
    hit = sum(r.cache_hit_tokens or 0 for r in rows)
    miss = sum(r.cache_miss_tokens or 0 for r in rows)
    tracked = hit + miss
    return {
        "calls": calls,
        "prompt_tokens": sum(r.prompt_tokens or 0 for r in rows),
        "completion_tokens": sum(r.completion_tokens or 0 for r in rows),
        "total_tokens": tokens,
        "cache_hit_tokens": hit,
        "cache_miss_tokens": miss,
        # 只在厂商确实回传了缓存拆分时才算命中率，否则 None（不假装有数据）
        "cache_hit_rate": round(hit / tracked, 4) if tracked else None,
        "estimated_calls": est_calls,
        "failed_calls": failed,
    }


def summary(db: Session, *, project_id: str | None = None, days: int = 30) -> dict:
    """聚合统计（用 Python 聚合——数据量小，且避免 SQL 日期函数的方言差异）。"""
    since = datetime.utcnow() - timedelta(days=max(1, int(days or 30)))
    q = db.query(LlmUsageLogORM).filter(LlmUsageLogORM.created_at >= since)
    if project_id:
        q = q.filter(LlmUsageLogORM.project_id == project_id)
    rows = q.order_by(LlmUsageLogORM.created_at.desc()).all()

    by_model: dict[str, list] = {}
    by_scene: dict[str, list] = {}
    by_day: dict[str, list] = {}
    for r in rows:
        by_model.setdefault(r.model_name or "（未记录）", []).append(r)
        by_scene.setdefault(r.scene or "（未记录）", []).append(r)
        by_day.setdefault(r.created_at.strftime("%Y-%m-%d") if r.created_at else "?", []).append(r)

    def _as_list(d: dict, key_name: str):
        out = []
        for k, v in d.items():
            item = {key_name: k}
            item.update(_bucket(v))
            out.append(item)
        out.sort(key=lambda x: -x["total_tokens"])
        return out

    trend = []
    for day in sorted(by_day.keys(), reverse=True)[:30]:
        item = {"date": day}
        item.update(_bucket(by_day[day]))
        trend.append(item)

    return {
        "days": days,
        "overall": _bucket(rows),
        "by_model": _as_list(by_model, "model_name"),
        "by_scene": _as_list(by_scene, "scene"),
        "trend": trend,
        "recent": [
            {
                "id": r.id,
                "scene": r.scene,
                "model_name": r.model_name,
                "vendor": r.vendor,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "cache_hit_tokens": r.cache_hit_tokens or 0,
                "cache_miss_tokens": r.cache_miss_tokens or 0,
                "estimated": r.estimated,
                "ok": r.ok,
                "duration_ms": r.duration_ms,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows[:50]
        ],
    }


def clear(db: Session, *, project_id: str | None = None) -> int:
    """清空用量日志（可选按项目）。返回删除行数。"""
    try:
        q = db.query(LlmUsageLogORM)
        if project_id:
            q = q.filter(LlmUsageLogORM.project_id == project_id)
        n = q.delete(synchronize_session=False)
        db.commit()
        return int(n or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[usage] 清空失败: {type(e).__name__}: {e}")
        try:
            db.rollback()
        except Exception as e2:  # noqa: BLE001
            logger.debug(f"[usage] rollback 失败: {type(e2).__name__}: {e2}")
        return 0
