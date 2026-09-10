"""应用装配冒烟：import main + 路由计数。

init_db() 只挂在 startup 事件上（main.py @app.on_event），
import 本身零副作用，不碰数据库——这是冒烟测试可以随意跑的原因。
"""
import main


def test_app_imports():
    assert main.app.title == "网页小说智能体 API"


def test_route_count_under_api_v1():
    n = sum(1 for r in main.app.routes
            if getattr(r, "path", "").startswith("/api/v1"))
    # 2026-09-09 基线：82 条全在 /api/v1 下；<80 说明路由装配残了
    assert n >= 80, f"/api/v1 routes = {n}"


def test_health_route_registered():
    paths = {getattr(r, "path", "") for r in main.app.routes}
    assert "/api/v1/health" in paths
