"""_dedup_trailing_repeats 反误杀回归（B11 修复的离线固化）。

素材全部来自 2026-09-09 实测轮次的真实文本（fixtures/）：
- bprime_streamed_20260909.txt  B' 轮流式全文（3018 字符/180 段）——
  旧实现误杀 97 段正常剧情的那份，结尾 hook「牙印上刻着"伍"」必须保住；
- final_green_20260909.txt      修复后 all-green 轮的落库文本；
- qwen35_baseline_20260909.txt  Qwen3.5-122B 基线轮文本。

旧实现病灶（B11）：单段字符集 Jaccard>0.8 即从此段全裁——
「沈砚看向水洼。」vs 75 段前的「沈砚看水洼。」Jaccard=0.857。
新规则：长段(≥20字) + difflib>0.8 + 连续≥3 段，三条同时满足才裁。
"""
from pathlib import Path

from app.routers.chapter import _dedup_trailing_repeats

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------- 真实文本：绝不误杀 ----------

def test_bprime_streamed_not_cut():
    """B' 轮流式全文（97 段曾被误杀）应原样通过，一个字都不能少。"""
    text = _load("bprime_streamed_20260909.txt")
    out = _dedup_trailing_repeats(text)
    assert out == text
    assert out.rstrip().endswith("牙印上刻着“伍”。")


def test_final_green_not_cut():
    """all-green 轮落库文本不应被裁。"""
    text = _load("final_green_20260909.txt")
    assert _dedup_trailing_repeats(text) == text


def test_qwen35_baseline_not_cut():
    """Qwen3.5-122B 基线文本不应被裁。"""
    text = _load("qwen35_baseline_20260909.txt")
    assert _dedup_trailing_repeats(text) == text


# ---------- 构造用例：该裁的要裁 ----------

def test_constructed_repetition_is_cut():
    """尾部连续 3 个相同长段 = 复读块，必须裁掉。"""
    # 六段内容必须真正不同——若只差序号，body 自身也会被判成复读块
    body = [
        "李慕白走进院子，看见石桌上摆着一壶凉透的茶，墙角的老槐树落了一地黄叶，他没说话，只把剑放在了桌上。",
        "陈砚从屋里出来，手里端着一碗粥，粥面上飘着两片葱花，他看了一眼桌上的剑，眉头皱了起来。",
        "院子外的风大了些，吹得槐树枝条乱摆，远处传来更夫的梆子声，一下，又一下。",
        "两人隔着石桌对望，谁都没先开口，粥碗上的热气慢慢散尽了。",
        "李慕白先笑了，他说这茶凉了三回，你才肯出来见我，架子不小。",
        "陈砚把碗放下，说茶凉可以续，人凉了就续不上了，你来做什么。",
    ]
    repeat = (
        "陈砚抬起头，眼睛里有血丝，手指按在桌沿上，指节泛白，"
        "他盯着李慕白看了很久，忽然笑了一声，笑声很轻。"
    )
    text = "\n\n".join(body + [repeat] * 3)
    out = _dedup_trailing_repeats(text)
    assert out == "\n\n".join(body)


# ---------- 最小复现：短段差一字不得再触发全裁 ----------

def test_one_char_diff_short_para_not_cut():
    """最小复现 B11：7 字短段差一字（Jaccard 0.857）不许触发裁剪。

    场景 A：全短段（短句呼应是正常写作手法）；
    场景 B：两个高相似长段被短段隔开（单段相似=呼应，连续才=复读）。
    """
    long_a = "他沿着河边走了半里地，风把袖口吹得猎猎作响，河面上浮着一层薄薄的雾气。"
    long_a2 = "他沿着河边走了半里地，风把袖口吹得猎猎作响，河面上浮着一层薄雾。"

    scenario_a = "\n\n".join([
        "沈砚看水洼。",                # 7 字，短段
        "庙里的风从门缝灌进来，油灯晃了两下。",
        "他数了数铜钱，还剩十一枚，不够住店。",
        "老陈头蹲在墙根下抽烟，烟锅一明一灭。",
        "雨停了，屋檐还在滴水，滴在青石板上。",
        "沈砚看向水洼。",              # 与首段差一字
        "远处传来打更的声音，三更了。",
        "他把油布包重新系好，塞回怀里。",
    ])
    assert _dedup_trailing_repeats(scenario_a) == scenario_a

    scenario_b = "\n\n".join([
        long_a,                        # 长段 A
        "他停下脚步。",
        "雾里有人影。",
        "沈砚攥紧了刀柄。",
        "那人开口了。",
        long_a2,                       # 与 A 相似度 >0.8 的长段，但被短段隔开
        "灯灭了。",
        "庙门吱呀一声开了。",
    ])
    assert _dedup_trailing_repeats(scenario_b) == scenario_b
