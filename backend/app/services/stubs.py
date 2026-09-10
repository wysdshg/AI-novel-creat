"""套路模板模块桩（placeholder）。

⚠️ 本文件在 Phase 3.1（2026-09-10）已从「全模块业务桩」收窄为**仅套路模板**：
原有 15 个函数中 13 个已确认 0 引用（各业务模块均已由真实 CRUD 实现），
已删除；保留的这两个仍被 `routers/template.py` 调用。

套路模板模块本身处于**冻结**状态（见 docs/03 §1）——7 条硬编码模板
题材绑定、不可编辑，与「题材无关」原则冲突，待设计定型后重做。
"""
import uuid


def _pid() -> str:
    return uuid.uuid4().hex


# ---------- 套路模板（冻结中，返回内置示意模板）----------
def list_templates() -> list:
    # TODO: 返回内置模板库（秘境夺宝/宗门大比/…）
    return [
        {"id": "tmpl_treasure", "name": "秘境夺宝", "description": "探索未知秘境争夺宝物"},
        {"id": "tmpl_tournament", "name": "宗门大比", "description": "门派比武扬名"},
        {"id": "tmpl_rebirth", "name": "穿越重生", "description": "携记忆重活一世"},
        {"id": "tmpl_revenge", "name": "复仇逆袭", "description": "弱者逆袭复仇"},
        {"id": "tmpl_mystery", "name": "悬疑探案", "description": "层层推理破案"},
        {"id": "tmpl_siege", "name": "团战突围", "description": "绝境团队协作破局"},
        {"id": "tmpl_urban", "name": "都市奇遇", "description": "都市中的奇遇成长"},
    ]


def generate_outline(project_id: str, payload: dict) -> dict:
    # TODO: AI 基于模板+历史摘要拆分大纲（每章核心/出场/伏笔位）
    return {"id": _pid(), "project_id": project_id, "template_id": payload.get("template_id"),
            "chapters": [], "status": "draft"}
