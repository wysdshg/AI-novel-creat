"""全模块业务桩（placeholder）。

约定：所有函数接收 project_id 等业务参数，返回 dict / list（与 schema 对齐）。
脚手架阶段不接数据库与模型，仅返回示意数据，并统一标记 TODO。
真实实现后，routers 不需改动调用方式，仅替换本文件函数体。
"""
import uuid
from datetime import datetime


def _pid() -> str:
    return uuid.uuid4().hex


# ---------- 作品 ----------
def create_project(payload: dict) -> dict:
    # TODO: 建表隔离（§1），落库 projects
    return {"id": _pid(), "chapter_count": 0, "created_at": datetime.utcnow().isoformat(), **payload}


def list_projects() -> list:
    # TODO: 查询 projects 表
    return []


# ---------- 资料库 ----------
def list_characters(project_id: str) -> list:
    # TODO: 查询 characters 表（应用表前缀隔离）
    return []


def create_character(project_id: str, payload: dict) -> dict:
    # TODO: 写入 characters 表 + 审计日志
    return {"id": _pid(), "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(), **payload}


def validate_settings(project_id: str, payload: dict) -> dict:
    # TODO: 拉取出场实体 → 生成约束清单 → 扫描正文 → 返回 issues
    return {"constraint_list": [], "issues": []}


def run_command(project_id: str, payload: dict) -> dict:
    # TODO: 指令解析引擎（正则+语义识别）→ 路由到对应 CRUD → 可选 dry_run
    return {"intent": None, "changes": [], "clarification": "指令解析引擎待接入"}


# ---------- 章节 / 商讨 ----------
def list_chapters(project_id: str) -> list:
    # TODO: 查询 chapters 表
    return []


def list_discussion(project_id: str) -> list:
    # TODO: 读取临时商讨缓存（Redis 或 discussion_messages）
    return []


def clear_discussion(project_id: str) -> None:
    # TODO: 清空临时商讨缓存
    return None


# ---------- 模型网关 ----------
def list_models() -> list:
    # TODO: 查询 model_configs 表
    return []


def create_model(payload: dict) -> dict:
    # TODO: 加密存储 api_key，落库 model_configs
    return {"id": _pid(), **payload}


def test_model(payload: dict) -> dict:
    # TODO: 通过 gateway/registry 获取适配器并 test_connection
    return {"ok": False, "latency_ms": 0, "msg": "模型适配器待接入"}


# ---------- 记忆压缩 ----------
def compress_memory(project_id: str, chapter_id: str) -> dict:
    # TODO: 调用 memory 角色模型做结构化压缩
    return {"chapter_no": 0, "core_event": "", "character_states": [],
            "new_foreshadows": [], "emotion_shift": "", "mainline_progress": ""}


def get_memory_summary(project_id: str) -> dict:
    # TODO: 取最近3章详细 + 更早极简大事记
    return {"recent": [], "events": []}


# ---------- 伏笔 ----------
def list_foreshadows(project_id: str, status: str | None = None) -> list:
    # TODO: 查询 foreshadows 表，可按 status 过滤
    return []


def detect_foreshadows(project_id: str, chapter_id: str) -> list:
    # TODO: AI 根据章节正文识别新增伏笔
    return []


def get_active_foreshadows(project_id: str) -> list:
    # TODO: 匹配当前剧情场景，筛出可触发伏笔
    return []


# ---------- 套路模板 ----------
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
