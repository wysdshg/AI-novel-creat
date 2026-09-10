"""Phase 3.5 护栏：禁止 `except Exception` 静默吞掉异常（无日志、无 raise）。

背景：Phase 3.5 清理前，`backend/app/**/*.py` 有 **107 处** `except Exception`，
其中 **53 处**是"吞掉异常且既不记日志也不 re-raise"——即出问题时**服务端完全无痕迹**，
只能靠用户描述"功能不工作"来猜。

清理后全部 107 处都满足以下三者之一：
1. 在 handler 体内调用 logger（含 `log.exception` / `logger.warning` 等）；
2. `raise`（把异常交给上层，由上层负责记录）——注意 `raise` 关键字即可，
   `raise X from e` 与裸 `raise` 都算；
3. 显式以 `# noqa: BLE001` 标注**并列明原因**（极少数确实不该记的情形，需人工评审）；
4. 属于**日志基础设施自身**（`app/core/logging_config.py`）——那里的 except 不能记日志，
   否则会二次失败/递归（详见该文件的 `_EXEMPT_FILES` 注释）。

本测试即锁定这一状态，防止回潮（新写的 except 一静默就红）。
"""
import ast
import pathlib

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "app"

# 允许的"无日志"白名单：文件相对路径 + 行号附近特征不做硬编码，
# 而是通过"是否有 noqa 注释"来判断——即在 handler 行或体内显式声明豁免。
_LOGGER_HINTS = ("logger.", "logging.", "log.")

# 整文件豁免：只限**日志基础设施自身**。
# 理由：`logging_config.py` 的 except 分支**不能调用 logging**——
#   · handler 还没建好（如 mkdir 失败）时再记日志 → 二次失败；
#   · 异常 hook 内部再记日志 → 可能递归触发 hook；
#   · 进程退出阶段记日志 → handler 可能已 shutdown。
# 这些分支的意图已在源码注释中说明（如"失败返回 None，不能拖垮服务启动"）。
# 除本文件外，其余模块一律适用静默禁令。
_EXEMPT_FILES = {"app/core/logging_config.py"}


def _handler_has_logging(body_src: str) -> bool:
    return any(h in body_src for h in _LOGGER_HINTS)


def _collect_broad_excepts():
    """返回 [(相对路径, 行号, 是否静默, body 摘要)]。"""
    found = []
    for path in sorted(APP_DIR.rglob("*.py")):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:  # pragma: no cover - 语法错误交给别的测试报
            continue
        lines = src.splitlines()
        rel = str(path.relative_to(APP_DIR.parent)).replace("\\", "/")
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            t = node.type
            # 只看 `except Exception`（含 `except Exception as e`）
            if not (isinstance(t, ast.Name) and t.id == "Exception"):
                continue
            body_src = "".join(
                (ast.get_source_segment(src, s) or "") + "\n" for s in node.body
            )
            has_log = _handler_has_logging(body_src)
            has_raise = "raise" in body_src
            # 该 except 行本身是否带 noqa 豁免标记
            line_text = lines[node.lineno - 1] if node.lineno - 1 < len(lines) else ""
            is_exempt = "noqa" in line_text.lower() or rel in _EXEMPT_FILES
            silent = (not has_log) and (not has_raise) and (not is_exempt)
            found.append((rel, node.lineno, silent, body_src.strip().splitlines()[:1]))
    return found


def test_no_silent_broad_except_in_app():
    """`backend/app/**/*.py` 里不允许存在『吞掉且不记日志、不 raise』的 except Exception。"""
    rows = _collect_broad_excepts()
    silent = [r for r in rows if r[2]]
    assert not silent, (
        "发现静默吞异常的 broad-except（Phase 3.5 禁止回潮）：\n"
        + "\n".join(f"  {f}:{ln}  {body}" for f, ln, _, body in silent)
    )


def test_broad_except_scan_actually_sees_handlers():
    """自检：扫描器必须真的抓到 broad-except，否则上面那条测试会因『扫不到』而假绿。"""
    rows = _collect_broad_excepts()
    assert len(rows) >= 80, (
        f"只扫到 {len(rows)} 处 broad-except，远少于预期（清理后实测 107 处）——"
        "扫描逻辑可能失效（例如 APP_DIR 找错），这条测试是防『假绿』的哨兵。"
    )
