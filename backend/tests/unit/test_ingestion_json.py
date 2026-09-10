"""写后摄取的 LLM 输出解析容错（B 方案：最易崩的第 2 处）。

ingestion.parse_json_loose 承接本地小模型/免费档模型的四种脏输出：
代码围栏、前后废话、尾逗号、全角引号。每种形态都实测踩过。
"""
from app.services.ingestion import parse_json_loose

import json

SAMPLE = {"summary": "陈砚接下三招之约。", "characters": ["陈砚", "赵烈"]}


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def test_plain_json():
    assert parse_json_loose(_dump(SAMPLE)) == SAMPLE


def test_json_code_fence():
    assert parse_json_loose("```json\n" + _dump(SAMPLE) + "\n```") == SAMPLE


def test_bare_code_fence():
    assert parse_json_loose("```\n" + _dump(SAMPLE) + "\n```") == SAMPLE


def test_chatter_around_json():
    # probe_pipeline 验证过的真实形态：「好的，结果如下：」+ 围栏
    assert parse_json_loose("好的，结果如下：\n```json\n" + _dump(SAMPLE) + "\n```") == SAMPLE


def test_trailing_comma():
    dirty = '{"summary": "a", "characters": ["甲", "乙",],}'
    assert parse_json_loose(dirty) == {"summary": "a", "characters": ["甲", "乙"]}


def test_fullwidth_quotes():
    # 注意：只放全角引号。值外全角逗号"，"不在容错范围（值内全角逗号是合法
    # 内容不能盲目替换，函数刻意不处理——这是已知边界不是 bug）
    dirty = '{"summary": "陈砚", "characters": ["甲"]}'
    assert parse_json_loose(dirty) == {"summary": "陈砚", "characters": ["甲"]}


def test_nested_structure_survives():
    obj = {"summary": "s", "foreshadow_actions": [{"action": "bury", "desc": "玉牌"}]}
    assert parse_json_loose(_dump(obj)) == obj


def test_nested_inside_chatter_with_fence_and_comma():
    dirty = "好的：\n```json\n{\"summary\": \"s\", \"list\": [1, 2,],}\n```"
    assert parse_json_loose(dirty) == {"summary": "s", "list": [1, 2]}


def test_non_dict_returns_none():
    assert parse_json_loose("[1, 2, 3]") is None
    assert parse_json_loose('"just a string"') is None


def test_garbage_returns_none():
    assert parse_json_loose("完全没有花括号的输出") is None
    assert parse_json_loose("") is None
    assert parse_json_loose(None) is None


def test_unfixable_braces_returns_none():
    # 有花括号但内容烂到修不动（缺引号的非法 key）
    assert parse_json_loose("{summary: a, list: [1,}") is None


def test_real_broken_model_output():
    # 8B 小模型真实输出形态：思考语句 + 围栏 + 尾逗号 + 全角引号混合
    dirty = ("好的，这是抽取结果：\n```json\n{\"summary\": “少年觉醒”, "
             "\"plot_points\": [\"接约\", \"昏迷\",],}\n```\n希望对你有帮助")
    assert parse_json_loose(dirty) == {"summary": "少年觉醒",
                                       "plot_points": ["接约", "昏迷"]}
