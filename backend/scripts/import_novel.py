"""小说导入 CLI（Phase 7.1）：目录 → 逐章概括 → 情节段 → 分类 → Markdown 报告。

供 OpenCode / 人工跑批。用法（在 backend/ 下执行）：

    ..\\.venv\\Scripts\\python.exe scripts/import_novel.py ^
        --book-dir "E:\\AI小说创作\\小说\\斗破苍穹 - 天蚕土豆" ^
        --book-name "斗破苍穹" --start 1 --end 50 --stage all

阶段（建议按书分开跑，出问题好定位）：
  summarize  逐章概括（最慢，幂等断点续跑：中断后重跑同一命令自动跳过已完成章）
  segment    情节段切分（重算会清旧段标记）
  label      段分类
  all        三连跑 + 报告

防限流：--interval 默认 2.0 秒（**禁止调小**），429/5xx 自动指数退避。
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # backend/
sys.stdout.reconfigure(encoding="utf-8")   # Windows 控制台中文输出

import app.core.database as dbmod                          # noqa: E402
from app.services import plot_import as pi                 # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="小说 → 概括 → 情节段 → 分类 → 报告")
    ap.add_argument("--book-dir", required=True, help="小说章节目录（形如 0001_标题.txt）")
    ap.add_argument("--book-name", required=True, help="入库用书名（断点续跑的幂等键）")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--stage", choices=["summarize", "segment", "label", "all"], default="all")
    ap.add_argument("--batch", type=int, default=10, help="段切分每批章数")
    ap.add_argument("--interval", type=float, default=2.0, help="请求最小间隔秒（防限流，禁止调小）")
    ap.add_argument("--out", default=None, help="报告输出路径（默认 outputs/<书名>-导入报告.md）")
    args = ap.parse_args()

    dbmod.init_db()
    db = dbmod.SessionLocal()
    rate = pi.RateLimiter(args.interval)
    t0 = time.time()

    if args.stage in ("summarize", "all"):
        st = pi.import_chapters(db, args.book_dir, args.book_name,
                                start=args.start, end=args.end, rate=rate)
        print(f"[summarize] {st}")
    if args.stage in ("segment", "all"):
        st = pi.segment_chapters(db, args.book_name, batch=args.batch, rate=rate)
        print(f"[segment] {st}")
    if args.stage in ("label", "all"):
        st = pi.label_segments(db, args.book_name, rate=rate)
        print(f"[label] {st}")

    path = pi.export_report(db, args.book_name, args.out)
    print(f"[report] {path}")
    print(f"[done] {time.time() - t0:.0f}s")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
