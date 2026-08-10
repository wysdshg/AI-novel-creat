"""去 AI 味引擎（需求 5）。

两条链路，互不依赖：

1) 前置注入 build_prompt_block()
   在章节生成时把最毒的那几类规则塞进系统提示词。刻意做得短——
   本地 4B 模型对超长规则清单的遵循率会断崖下跌，塞得越多反而越糊。

2) 后置检测 scan()
   纯正则扫描，**不调模型**。所以它不会把写好的句子改崩，也不花 token。
   输出问题清单 + 自然度评分，改不改由作者决定。

之所以不做「模型二次改写」：本地 4B 二改会丢细节、把生动的句子改平，
风险远大于收益。等换云端强模型后再开这条链路也不迟。
"""
import re
from typing import Any

from app.core.banned_words import (
    TOXIC_PATTERNS,
    L1_WORDS,
    STACKED_ADVERBS,
    ADVERB_REPEAT_THRESHOLD,
    ADVERB_DENSITY_THRESHOLD,
    CLICHE_METAPHORS,
    SUMMARY_PATTERNS,
    REPLACE_STRATEGY,
    NOVEL_OOC_RULES,
)

# 严重度权重：算综合分用
_SEVERITY_WEIGHT = {"high": 5.0, "medium": 2.0, "low": 0.5}
# 上下文摘录半径（字符）
_CONTEXT_RADIUS = 18


# ===========================================================================
# 后置检测
# ===========================================================================

def _context_of(text: str, start: int, end: int) -> str:
    left = max(0, start - _CONTEXT_RADIUS)
    right = min(len(text), end + _CONTEXT_RADIUS)
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(text) else ""
    return f"{prefix}{text[left:right]}{suffix}".replace("\n", " ")


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _overlaps(span: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
    """命中区间是否已被更高优先级的规则覆盖。

    「仿佛……一般」会同时命中句式规则和情态词「仿佛」，
    只报前者，避免同一处问题重复刷屏。
    """
    s, e = span
    for os_, oe in occupied:
        if s < oe and e > os_:
            return True
    return False


def _scan_patterns(text: str, rules: list[dict], scene: str,
                   occupied: list[tuple[int, int]]) -> list[dict]:
    issues: list[dict] = []
    for rule in rules:
        if scene not in rule.get("scenes", ["novel", "article"]):
            continue
        try:
            regex = re.compile(rule["pattern"])
        except re.error:
            continue
        for m in regex.finditer(text):
            span = (m.start(), m.end())
            if _overlaps(span, occupied):
                continue
            occupied.append(span)
            issues.append({
                "rule_id": rule["id"],
                "name": rule["name"],
                "category": rule.get("category", "句式"),
                "severity": rule["severity"],
                "matched": m.group(0)[:60],
                "start": m.start(),
                "end": m.end(),
                "line": _line_of(text, m.start()),
                "context": _context_of(text, m.start(), m.end()),
                "advice": rule["advice"],
            })
    return issues


def _scan_words(text: str, scene: str, occupied: list[tuple[int, int]]) -> list[dict]:
    issues: list[dict] = []
    for group_name, group in L1_WORDS.items():
        if scene not in group.get("scenes", ["novel", "article"]):
            continue
        severity = group["severity"]
        advice = group["advice"]
        for word in group["words"]:
            start = 0
            while True:
                idx = text.find(word, start)
                if idx < 0:
                    break
                span = (idx, idx + len(word))
                start = idx + len(word)
                if _overlaps(span, occupied):
                    continue
                occupied.append(span)
                issues.append({
                    "rule_id": f"word.{group_name}.{word}",
                    "name": f"禁用词「{word}」",
                    "category": group_name,
                    "severity": severity,
                    "matched": word,
                    "start": span[0],
                    "end": span[1],
                    "line": _line_of(text, span[0]),
                    "context": _context_of(text, span[0], span[1]),
                    "advice": advice,
                })
    return issues


def _scan_cliche(text: str, occupied: list[tuple[int, int]]) -> list[dict]:
    issues: list[dict] = []
    for phrase in CLICHE_METAPHORS:
        start = 0
        while True:
            idx = text.find(phrase, start)
            if idx < 0:
                break
            span = (idx, idx + len(phrase))
            start = idx + len(phrase)
            if _overlaps(span, occupied):
                continue
            occupied.append(span)
            issues.append({
                "rule_id": f"cliche.{phrase}",
                "name": f"陈词滥调比喻「{phrase}」",
                "category": "比喻",
                "severity": "high",
                "matched": phrase,
                "start": span[0],
                "end": span[1],
                "line": _line_of(text, span[0]),
                "context": _context_of(text, span[0], span[1]),
                "advice": "本体与喻体没有真实逻辑关联，是词语表面相似性拼接。改白描或直接删。",
            })
    return issues


def _scan_adverb_stacking(text: str) -> list[dict]:
    """副词堆叠是段落级问题：单个「猛地」无罪，一段里三个「猛地」就是AI。"""
    issues: list[dict] = []
    offset = 0
    for para in text.split("\n"):
        stripped = para.strip()
        if len(stripped) < 40:
            offset += len(para) + 1
            continue
        hits: dict[str, int] = {}
        for adv in STACKED_ADVERBS:
            c = para.count(adv)
            if c:
                hits[adv] = c
        repeated = {w: c for w, c in hits.items() if c >= ADVERB_REPEAT_THRESHOLD}
        total = sum(hits.values())
        if repeated:
            detail = "、".join(f"{w}×{c}" for w, c in sorted(repeated.items(), key=lambda x: -x[1]))
            issues.append({
                "rule_id": "adverb.repeat",
                "name": "同一副词段内重复",
                "category": "副词堆叠",
                "severity": "medium",
                "matched": detail,
                "start": offset,
                "end": offset + len(para),
                "line": _line_of(text, offset),
                "context": stripped[:60] + ("…" if len(stripped) > 60 else ""),
                "advice": f"本段 {detail}。同一副词一段里只留一次，其余换动作或删。",
            })
        elif total >= ADVERB_DENSITY_THRESHOLD:
            detail = "、".join(sorted(hits.keys()))
            issues.append({
                "rule_id": "adverb.density",
                "name": "副词密度过高",
                "category": "副词堆叠",
                "severity": "low",
                "matched": detail,
                "start": offset,
                "end": offset + len(para),
                "line": _line_of(text, offset),
                "context": stripped[:60] + ("…" if len(stripped) > 60 else ""),
                "advice": f"本段堆了 {total} 个强调副词（{detail}）。砍掉一半，让动词自己发力。",
            })
        offset += len(para) + 1
    return issues


def _grade(score: float) -> str:
    if score >= 90:
        return "自然"
    if score >= 75:
        return "轻微AI味"
    if score >= 55:
        return "明显AI味"
    return "严重AI味"


def scan(text: str, scene: str = "novel") -> dict[str, Any]:
    """扫描文本的 AI 味问题，返回结构化报告。

    scene: novel（小说正文，不套用标点/议论连接词禁令） | article（自媒体长文）
    """
    text = text or ""
    if not text.strip():
        return {
            "score": 100, "grade": "自然", "char_count": 0,
            "issue_count": 0, "severity_stats": {"high": 0, "medium": 0, "low": 0},
            "issues": [], "top_offenders": [], "scene": scene,
        }

    occupied: list[tuple[int, int]] = []
    issues: list[dict] = []
    # 顺序即优先级：毒句式 > 结构 > 陈词比喻 > 单词
    issues += _scan_patterns(text, TOXIC_PATTERNS, scene, occupied)
    issues += _scan_patterns(text, SUMMARY_PATTERNS, scene, occupied)
    issues += _scan_cliche(text, occupied)
    issues += _scan_words(text, scene, occupied)
    # 段落级检测独立统计，不参与区间抑制
    issues += _scan_adverb_stacking(text)

    issues.sort(key=lambda x: x["start"])

    stats = {"high": 0, "medium": 0, "low": 0}
    for i in issues:
        stats[i["severity"]] = stats.get(i["severity"], 0) + 1

    chars = len(text)
    per_k = max(chars / 1000.0, 0.5)
    penalty = sum(_SEVERITY_WEIGHT.get(i["severity"], 1.0) for i in issues) / per_k
    score = max(0.0, min(100.0, 100.0 - penalty * 2.2))

    counter: dict[str, dict] = {}
    for i in issues:
        key = i["name"]
        if key not in counter:
            counter[key] = {"name": key, "count": 0, "severity": i["severity"], "advice": i["advice"]}
        counter[key]["count"] += 1
    top = sorted(counter.values(), key=lambda x: -x["count"])[:8]

    return {
        "score": round(score, 1),
        "grade": _grade(score),
        "char_count": chars,
        "issue_count": len(issues),
        "per_thousand": round(len(issues) / per_k, 2),
        "severity_stats": stats,
        "issues": issues,
        "top_offenders": top,
        "scene": scene,
    }


# ===========================================================================
# 前置注入
# ===========================================================================

_CORE_BANS_NOVEL = [
    "「不是A，而是B」句式——一次都不许出现。",
    "「眼中闪过一丝」「嘴角勾起一抹」「心中涌起」「心头一震」——全部禁用，改成可观察的具体动作。",
    "「仿佛/犹如……一般」的比喻壳——删掉，直接白描。",
    "「，带着一丝……」这种万能状语补丁——拆成短句。",
    "「这一刻他终于明白」「他不知道的是」这类总结升华与空泛预告——禁止。",
    "「声音不大，却带着不容置疑的力量」这一整类——「声音很平」三个字已是AI鉴定词。",
    "同一段里同一个强调副词（猛地/死死/瞬间/骤然/顿时）只准出现一次。",
]

_CRAFT_RULES_NOVEL = [
    "情绪一律外化：写「手在抖」不写「他很紧张」，写「攥紧拳头」不写「他感到愤怒」。",
    "认知一律用行为体现：不写「他知道来不及了」，写他做了什么。",
    "形容词能删就删：「白色的药片」→「药片」，「美丽动人的笑容」→「她笑了」。",
    "比喻要有真实生活逻辑，宁可不用也不要「命运的齿轮」「如潮水般涌来」这类套话。",
    "章节收尾用具体的物件、动作或一句台词收住，不要用抒情总结。",
    "句子长短交错，避免连续三句同样节奏的排比。",
]


def build_prompt_block(scene: str = "novel", level: str = "normal") -> str:
    """生成注入系统提示词的去 AI 味段落。

    level:
      light  只给最毒的 4 条（4B 模型 / 上下文吃紧时用）
      normal 毒句式 + 写法准则（默认）
      strict 再加 OOC 防护与替换策略表（云端强模型时用）
    """
    if scene != "novel":
        # 自媒体长文场景：换一套禁令（连接词、三段式、讨好腔）
        bans = [
            "禁用「值得注意的是」「不难发现」「综上所述」「说白了」「本质上」这类填充短语。",
            "禁用「首先/其次/最后」三段式，用隐性连接。",
            "禁用自问自答（「这叫什么？这叫……」），直接陈述。",
            "禁用「你以为A，实际上B」。",
            "不得写「相关研究表明」「据某报告显示」这类查无实据的引用。",
        ]
        return (
            "\n\n【去 AI 味硬约束】\n"
            + "\n".join(f"- {b}" for b in bans)
            + "\n- 写完自查一遍：凡是删掉之后不影响语义的词，就该删掉。"
        )

    bans = _CORE_BANS_NOVEL[:4] if level == "light" else _CORE_BANS_NOVEL
    block = (
        "\n\n【去 AI 味硬约束——违反任意一条都算本章不合格】\n"
        + "\n".join(f"- {b}" for b in bans)
    )
    if level == "light":
        return block

    block += "\n\n【写法准则】\n" + "\n".join(f"- {r}" for r in _CRAFT_RULES_NOVEL)

    if level == "strict":
        block += "\n\n【人设与设定保护】\n" + "\n".join(f"- {r}" for r in NOVEL_OOC_RULES)
        block += "\n\n【替换对照】\n" + "\n".join(
            f"- {a}：{b}（例：{c}）" for a, b, c in REPLACE_STRATEGY[:6]
        )
    return block


def quick_stats(text: str, scene: str = "novel") -> dict:
    """轻量统计：只要分数和条数，不要问题明细（列表页/生成完的一句话提示用）。"""
    r = scan(text, scene)
    return {
        "score": r["score"],
        "grade": r["grade"],
        "issue_count": r["issue_count"],
        "severity_stats": r["severity_stats"],
        "top_offenders": r["top_offenders"][:3],
    }
