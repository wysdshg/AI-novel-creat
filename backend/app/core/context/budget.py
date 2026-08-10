"""上下文预算与裁剪。

为什么必须有这一层：写到第 80 章时，全量角色卡 + 全部设定 + 所有伏笔
+ 历史记忆轻松突破十万字符，任何模型都装不下。硬塞的结果是模型截断，
而且截掉的往往是排在最后的、最重要的本章要求。

所以顺序反过来：**先按重要性排定去留，再拼接**。
不重要的整块丢掉，也不能让本章要点被挤出窗口。

字符 vs token：中文大致 1 token ≈ 1.5 字符，但各家分词器不同。
这里统一用字符做预算单位——口径稳定、可解释，也不用引入 tokenizer 依赖。
"""
from dataclasses import dataclass, field

# 三档预算（字符）。standard 对应约 20K token，主流 32K 窗口模型的安全线。
BUDGET_LEVELS: dict[str, int] = {
    "tight": 8_000,      # 本地小模型 / 追求速度
    "standard": 32_000,  # 默认
    "loose": 120_000,    # 云端长窗口模型
}

# 优先级常量，数值越大越重要，裁剪时最后动它
P_CRITICAL = 1000   # 本章要点、输出格式——丢了就没法写了
P_SKILL = 900       # 写作 SKILL（含去 AI 味硬约束）
P_CONTINUITY = 800  # 上一章结尾 + 结尾钩子，接不上就是断片
P_DISCUSSION = 700  # 作者刚聊过的剧情共识
P_CHARACTER = 600   # 角色卡
P_WORLD = 500       # 世界观、境界体系、概览
P_FORESHADOW = 450  # 待激活伏笔
P_MEMORY_RECENT = 400  # 最近几章记忆
P_MEMORY_STAGE = 300   # 阶段滚动摘要
P_ENTITY = 250      # 势力 / 地点 / 关系
P_REFERENCE = 200   # 参考文档，量最大且最可牺牲


@dataclass
class Block:
    """一段可独立取舍的上下文。"""
    key: str                 # 稳定标识，用于调试与前端展示
    title: str               # 人类可读的段落名
    content: str             # 正文
    priority: int            # 越大越保
    order: int = 0           # 最终拼接顺序（与优先级解耦）
    min_chars: int = 0       # 允许截断到的下限；0 表示要么全留要么整块丢
    required: bool = False   # True 时永不丢弃（超预算也保留）

    @property
    def size(self) -> int:
        return len(self.content or "")


@dataclass
class BudgetPlan:
    """裁剪结果。除了拼好的文本，也把取舍过程留痕，方便排查『为什么模型不知道这个设定』。"""
    blocks: list[Block] = field(default_factory=list)      # 最终保留（可能已截断）
    dropped: list[dict] = field(default_factory=list)      # 被整块丢弃
    truncated: list[dict] = field(default_factory=list)    # 被截断
    used_chars: int = 0
    budget: int = 0
    level: str = "standard"

    def render(self) -> str:
        parts = []
        for b in sorted(self.blocks, key=lambda x: (x.order, -x.priority)):
            body = (b.content or "").strip()
            if body:
                parts.append(f"{b.title}\n{body}")
        return "\n\n".join(parts)

    def debug(self) -> dict:
        return {
            "level": self.level,
            "budget": self.budget,
            "used": self.used_chars,
            "usage_pct": round(self.used_chars / self.budget * 100, 1) if self.budget else 0,
            "kept": [
                {"key": b.key, "chars": b.size, "priority": b.priority}
                for b in sorted(self.blocks, key=lambda x: -x.priority)
            ],
            "truncated": self.truncated,
            "dropped": self.dropped,
        }


def _truncate_at_boundary(text: str, limit: int) -> str:
    """在段落/句子边界截断，避免把句子劈成半截喂给模型。"""
    if len(text) <= limit:
        return text
    head = text[:limit]
    for sep in ("\n\n", "\n", "。", "；", "，"):
        idx = head.rfind(sep)
        # 至少保住 60% 的配额，否则宁可硬截
        if idx > limit * 0.6:
            return head[: idx + len(sep)].rstrip()
    return head


def plan_budget(blocks: list[Block], level: str = "standard") -> BudgetPlan:
    """按优先级分配预算。

    算法：
    1. required 块先无条件占位；
    2. 其余按 priority 降序依次装入；
    3. 装不下时，若允许截断（min_chars > 0）就截到剩余额度，
       剩余额度连 min_chars 都不够则整块丢弃；
    4. 全程记录取舍，供 debug 输出。
    """
    budget = BUDGET_LEVELS.get(level, BUDGET_LEVELS["standard"])
    plan = BudgetPlan(budget=budget, level=level)

    ordered = sorted(blocks, key=lambda b: (not b.required, -b.priority))
    used = 0

    for b in ordered:
        if not (b.content or "").strip():
            continue

        if b.required:
            plan.blocks.append(b)
            used += b.size
            continue

        remaining = budget - used
        if remaining <= 0:
            plan.dropped.append({"key": b.key, "chars": b.size, "reason": "预算已耗尽"})
            continue

        if b.size <= remaining:
            plan.blocks.append(b)
            used += b.size
            continue

        # 装不下：能截就截
        if b.min_chars and remaining >= b.min_chars:
            cut = _truncate_at_boundary(b.content, remaining)
            note = f"\n…（本段因上下文预算限制已截断，原长 {b.size} 字符）"
            if len(cut) + len(note) <= remaining:
                cut += note
            plan.truncated.append({"key": b.key, "from": b.size, "to": len(cut)})
            plan.blocks.append(Block(
                key=b.key, title=b.title, content=cut,
                priority=b.priority, order=b.order,
                min_chars=b.min_chars, required=b.required,
            ))
            used += len(cut)
        else:
            plan.dropped.append({
                "key": b.key, "chars": b.size,
                "reason": f"剩余额度 {remaining} 不足最小保留量 {b.min_chars or b.size}",
            })

    plan.used_chars = used
    return plan
