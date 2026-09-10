"""humanizer.scan 打分回归（素材取自 probe_pipeline.py 第 7 组实测）。

AI 味坏样本 < 40 分、人写好样本 > 85 分——与 e2e 报告同一条合格线。
"""
from app.services import humanizer

BAD = ("他的眼中闪过一丝复杂的神色，仿佛看透了一切。这不是简单的挑衅，"
       "而是赤裸裸的羞辱。他知道，这一刻，他终于明白了什么叫做实力。"
       "空气仿佛凝固了一般，带着一丝不易察觉的压迫感。")
GOOD = ("赵烈把剑插进土里，剑柄还在晃。他说三招，接得住就算你赢。"
        "陈砚看了看那把剑，又看了看自己的手，慢慢把袖子挽上去。周围没人说话。")


def test_ai_flavored_sample_scores_low():
    r = humanizer.scan(BAD)
    assert r["score"] < 40, f"score={r['score']} issues={r['issue_count']}"


def test_human_sample_no_false_positive():
    r = humanizer.scan(GOOD)
    assert r["score"] > 85, f"score={r['score']} issues={r['issue_count']}"


def test_empty_text_returns_full_score():
    r = humanizer.scan("")
    assert r["score"] == 100


def test_report_shape():
    """返回结构契约：score/grade/char_count/issue_count 必须在。"""
    r = humanizer.scan(GOOD)
    for key in ("score", "grade", "char_count", "issue_count"):
        assert key in r, f"missing key: {key}"
