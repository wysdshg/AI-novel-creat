"""工作流节点公共工具：LLM 配置组装（从 chapter.py 提炼的已验证逻辑）。

⚠️ 2026-08-14 实测结论（A/B 对照）：
ModelScope Qwen3.5-122B 长生成时 frequency/presence_penalty=0.4 会触发中后段
采样退化（无标点长段 + 人名变拼音 + 夹英文），该组合默认惩罚归零。
ollama 用 repeat_penalty=1.3；其余厂商 0.4。env 可显式覆盖。
"""
import os
import re
from typing import Optional


def _similarity(a: str, b: str) -> float:
    """简单的字符级 Jaccard 相似度（用于段落去重判断）。"""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


def dedup_trailing_repeats(text: str) -> str:
    """剪掉尾部重复段落（与 chapter.py 的 _dedup_trailing_repeats 同源）。"""
    paras = re.split(r'\n\n+', text.strip())
    if len(paras) < 3:
        return text
    kept = list(paras)
    i = len(kept) - 2
    while i >= 0:
        current = kept[i].strip()
        if not current:
            i -= 1
            continue
        dup_start = -1
        for j in range(i):
            if _similarity(current, kept[j].strip()) > 0.8:
                dup_start = i
                break
        if dup_start >= 0:
            kept = kept[:dup_start]
            i = len(kept) - 2
        else:
            i -= 1
    return '\n\n'.join(kept)


def _modelscope_qwen35(model_name: str, api_base: str) -> bool:
    """ModelScope Qwen3.x 系列特判（惩罚归零 + 强关 thinking）。

    2026-09-09 放宽：原 "qwen3.5" 字面匹配在换 Qwen3.8-Flash-Next 后失配，
    惩罚回落 0.4/0.4 实测复现退化（标点密度 0.013、最长无标点段 1870 字）。
    改为正则匹配 qwen3.x 全系。函数名保留旧名以减少调用点改动。
    """
    return bool(
        re.search(r"qwen3\.\d", (model_name or "").lower())
        and "modelscope" in (api_base or "").lower()
    )


def resolve_penalty(vendor: str, model_name: str, api_base: str) -> dict:
    """返回重复惩罚参数（按厂商/模型组合）。"""
    vendor = (vendor or "").lower()
    rep_env = os.environ.get("NA_CHAPTER_REP_PENALTY")
    if rep_env:
        rep = float(rep_env)
    elif vendor == "ollama":
        rep = 1.3
    elif _modelscope_qwen35(model_name, api_base):
        rep = 0.0
    else:
        rep = 0.4
    if vendor == "ollama":
        return {"repeat_penalty": rep}
    return {
        "frequency_penalty": rep,
        "presence_penalty": float(
            os.environ.get(
                "NA_CHAPTER_PRES_PENALTY",
                "0.0" if _modelscope_qwen35(model_name, api_base) else "0.4",
            )
        ),
    }


def resolve_thinking(
    vendor: str,
    model_name: str,
    api_base: str,
    configured: Optional[bool],
    requested: Optional[bool] = None,
) -> Optional[bool]:
    """决定是否开启思考（从 chapter.py 提炼，含 ModelScope Qwen3.5 强关逻辑）。"""
    want = requested if requested is not None else configured
    vendor = (vendor or "").lower()
    # ModelScope Qwen3.5：thinking 会把英文 reasoning 塞进 content → 强制关闭
    if _modelscope_qwen35(model_name, api_base):
        return False
    # 云端推理模型关思考写长文必复读 → 章节类长生成强制开思考（ollama 除外）
    if (
        want is not True
        and os.environ.get("NA_CHAPTER_FORCE_THINKING", "1") == "1"
        and vendor != "ollama"
    ):
        return True
    return want


def chapter_max_tokens(target_words: int) -> int:
    """章节目标字数 → token 上限（中文 1 字 ≈ 1.2 token + 余量，硬顶 8192）。"""
    target_words = target_words or 5000
    hard_cap = int(os.environ.get("NA_CHAPTER_MAX_TOKENS", "8192"))
    return min(int(target_words * 1.2) + 256, hard_cap)


def build_llm_config(
    model_cfg: dict,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    enable_thinking: Optional[bool] = None,
) -> dict:
    """把 ModelConfigORM 标量 dict + 运行参数组装成 adapter config。

    model_cfg 字段: id/vendor/api_base/api_key/model_name/top_p/max_tokens/enable_thinking。
    """
    cfg = {
        "api_base": model_cfg.get("api_base"),
        "api_key": model_cfg.get("api_key"),
        "model_name": model_cfg.get("model_name"),
        "temperature": temperature if temperature is not None else model_cfg.get("temperature", 0.75),
        "top_p": model_cfg.get("top_p"),
        "max_tokens": max_tokens or model_cfg.get("max_tokens") or 4096,
    }
    want = resolve_thinking(
        model_cfg.get("vendor", ""),
        model_cfg.get("model_name", ""),
        model_cfg.get("api_base", ""),
        model_cfg.get("enable_thinking"),
        enable_thinking,
    )
    cfg["enable_thinking"] = want
    cfg.update(resolve_penalty(model_cfg.get("vendor", ""), model_cfg.get("model_name", ""), model_cfg.get("api_base", "")))
    return cfg
