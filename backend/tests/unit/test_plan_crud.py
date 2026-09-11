"""Phase 7.2 篇规划：生成 / 防幻觉闸门 / 行级修改 / 拍板 / 无 Key 报错。

全部 mock LLM（不出网）。防幻觉闸门是重点：召回角色必须真实存在于 characters 表。
"""
import json

import pytest

import app.core.database as dbmod
from app.models.orm import ArticlePlanORM, ArticleORM, VolumeORM, ProjectORM, CharacterORM
from app.services import plan_crud


@pytest.fixture()
def proj(test_db):
    p = ProjectORM(id="p1", name="测试作品")
    v = VolumeORM(id="v1", project_id="p1", name="第一卷", summary="卷概要")
    a = ArticleORM(id="a1", project_id="p1", volume_id="v1", name="第一篇", summary="篇概要")
    test_db.add_all([p, v, a])
    test_db.commit()
    return {"pid": p.id, "aid": a.id}


@pytest.fixture()
def with_key(monkeypatch):
    monkeypatch.setattr(plan_crud, "ds_key", lambda db: "ds-key")


def _payload():
    return json.dumps({"lines": [
        {"no": 1, "beat": "退婚立局", "summary": "主角被退婚当众羞辱，立下三年之约",
         "new_chars": ["纳兰嫣然"], "recall_chars": [], "target_words": 3000,
         "hook": "神秘老者现身", "template_ref": "退婚逆袭·开局"},
        {"no": 2, "beat": "密室机缘", "summary": "主角在房中发现老者遗物，开启戒指",
         "new_chars": [], "recall_chars": ["药老"], "target_words": 3000,
         "hook": "戒指里有东西", "template_ref": "退婚逆袭·发展"},
        {"no": 3, "beat": "吸收功力", "summary": "老者传授功法，实力暴涨",
         "new_chars": [], "recall_chars": ["不存在的人"], "target_words": 3000,
         "hook": "约期将至", "template_ref": "退婚逆袭·高潮"},
    ], "notes": "整体说明"}, ensure_ascii=False)


class TestGeneratePlan:
    def test_generate_ok(self, test_db, proj, with_key, monkeypatch):
        monkeypatch.setattr(plan_crud, "_ds_post", lambda k, c, **kw: _payload())
        st = plan_crud.generate_plan(test_db, proj["pid"], proj["aid"], hint="退婚流开局")
        assert st["lines"] == 3
        row = test_db.query(ArticlePlanORM).one()
        assert row.status == "draft" and row.origin in ("template", "free")
        assert row.plan["lines"][0]["beat"] == "退婚立局"

    def test_recall_chars_validated(self, test_db, proj, with_key, monkeypatch):
        """防幻觉闸门：召回角色必须真实存在，查无此人剔除。"""
        test_db.add(CharacterORM(id="c1", project_id="p1", name="药老"))
        test_db.commit()
        monkeypatch.setattr(plan_crud, "_ds_post", lambda k, c, **kw: _payload())
        st = plan_crud.generate_plan(test_db, proj["pid"], proj["aid"])
        assert st["unknown_chars"] == ["不存在的人"]
        row = test_db.query(ArticlePlanORM).one()
        lines = {l["no"]: l for l in row.plan["lines"]}
        assert lines[2]["recall_chars"] == ["药老"]           # 真实存在 → 保留
        assert lines[3]["recall_chars"] == []                 # 查无此人 → 剔除
        assert lines[1]["new_chars"] == ["纳兰嫣然"]          # 新角色不校验（走待确认实体）

    def test_regen_overwrites_draft(self, test_db, proj, with_key, monkeypatch):
        monkeypatch.setattr(plan_crud, "_ds_post", lambda k, c, **kw: _payload())
        plan_crud.generate_plan(test_db, proj["pid"], proj["aid"])
        plan_crud.generate_plan(test_db, proj["pid"], proj["aid"])
        assert test_db.query(ArticlePlanORM).count() == 1     # 同一篇只有一条当前计划

    def test_no_key_raises(self, test_db, proj, monkeypatch):
        monkeypatch.setattr(plan_crud, "ds_key", lambda db: None)
        try:
            plan_crud.generate_plan(test_db, proj["pid"], proj["aid"])
            raised = False
        except RuntimeError as e:
            raised = "Key" in str(e)
        assert raised

    def test_bad_output_raises(self, test_db, proj, with_key, monkeypatch):
        monkeypatch.setattr(plan_crud, "_ds_post", lambda k, c, **kw: "这不是 JSON")
        try:
            plan_crud.generate_plan(test_db, proj["pid"], proj["aid"])
            raised = False
        except RuntimeError as e:
            raised = "计划生成失败" in str(e)
        assert raised


class TestPlanWorkflow:
    def _gen(self, test_db, proj, with_key, monkeypatch):
        monkeypatch.setattr(plan_crud, "_ds_post", lambda k, c, **kw: _payload())
        plan_crud.generate_plan(test_db, proj["pid"], proj["aid"])

    def test_refine_line_only_changes_target(self, test_db, proj, with_key, monkeypatch):
        self._gen(test_db, proj, with_key, monkeypatch)
        monkeypatch.setattr(plan_crud, "_ds_post", lambda k, c, **kw: json.dumps({
            "no": 2, "beat": "密室机缘（改）", "summary": "改后的概要，信息量足够长一些。",
            "new_chars": [], "recall_chars": ["药老"], "target_words": 3500,
            "hook": "新钩子", "template_ref": "退婚逆袭·发展"}, ensure_ascii=False))
        r = plan_crud.refine_line(test_db, proj["pid"], proj["aid"], line_no=2,
                                  instruction="节奏放缓，加重悬念")
        assert r["line"]["beat"] == "密室机缘（改）"
        plan = plan_crud.get_plan(test_db, proj["pid"], proj["aid"])
        by_no = {l["no"]: l for l in plan["lines"]}
        assert by_no[1]["summary"].startswith("主角被退婚")   # 其他行不动
        assert by_no[2]["target_words"] == 3500
        assert by_no[3]["beat"] == "吸收功力"

    def test_refine_line_missing_no_raises(self, test_db, proj, with_key, monkeypatch):
        self._gen(test_db, proj, with_key, monkeypatch)
        try:
            plan_crud.refine_line(test_db, proj["pid"], proj["aid"], line_no=99,
                                  instruction="改")
            raised = False
        except RuntimeError:
            raised = True
        assert raised

    def test_confirm_then_get(self, test_db, proj, with_key, monkeypatch):
        self._gen(test_db, proj, with_key, monkeypatch)
        r = plan_crud.confirm_plan(test_db, proj["pid"], proj["aid"])
        assert r["status"] == "confirmed"
        plan = plan_crud.get_plan(test_db, proj["pid"], proj["aid"])
        assert plan["status"] == "confirmed"

    def test_save_lines_edit(self, test_db, proj, with_key, monkeypatch):
        self._gen(test_db, proj, with_key, monkeypatch)
        plan = plan_crud.get_plan(test_db, proj["pid"], proj["aid"])
        lines = plan["lines"]
        lines[0]["summary"] = "作者手改后的概要，长度足够通过校验。"
        plan_crud.save_lines(test_db, proj["pid"], proj["aid"], lines=lines, notes="作者批注")
        got = plan_crud.get_plan(test_db, proj["pid"], proj["aid"])
        assert got["lines"][0]["summary"].startswith("作者手改")
        assert got["notes"] == "作者批注"

    def test_no_plan_returns_none(self, test_db, proj):
        assert plan_crud.get_plan(test_db, proj["pid"], proj["aid"]) is None
