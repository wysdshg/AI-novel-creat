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
    ap = argparse.ArgumentParser(description="小说 → 概括 → 情节段 → 分类 → 故事弧 → 报告 / 模板凝练")
    ap.add_argument("--book-dir", default=None, help="小说章节目录（形如 0001_标题.txt）")
    ap.add_argument("--book-name", default=None,
                    help="入库用书名（断点续跑的幂等键）；distill 阶段省略 = 对全部书凝练")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--stage",
                    choices=["summarize", "segment", "label", "arc", "anonymize",
                             "distill", "all"],
                    default="all",
                    help="summarize 逐章概括 / segment 情节段 / label 段分类 / arc 故事弧 / "
                         "anonymize 专名匿名化（概括之后跑）/ distill 凝练模板 / all 前四步+报告")
    ap.add_argument("--batch", type=int, default=10, help="段切分每批章数")
    ap.add_argument("--threshold", type=float, default=0.80,
                    help="弧聚类相似度阈值（distill 用，越大越保守）")
    ap.add_argument("--min-arcs", type=int, default=1,
                    help="成组最少弧数（distill 用；设 2 = 只要跨书/跨弧的套路）")
    ap.add_argument("--batch-summarize", type=int, default=1,
                    help="每 N 章一次概括调用（默认 1=逐章；建议 3 —— 请求数降 1/N，跨章更连贯）")
    ap.add_argument("--concurrency", type=int, default=1,
                    help="并发批次数（默认 1=串行；建议 2~3 —— 瓶颈是等生成，并发才能提速）")
    ap.add_argument("--force", action="store_true",
                    help="段切分强制清空重算（默认 False = 断点续跑，跳过已完成批次）")
    ap.add_argument("--interval", type=float, default=2.0, help="请求发起最小间隔秒（防限流，禁止调小）")
    ap.add_argument("--out", default=None, help="报告输出路径（默认 outputs/<书名>-导入报告.md）")
    args = ap.parse_args()

    # 校验：除 distill（跨书凝练）外，其余阶段都必须指定书
    if args.stage != "distill" and not (args.book_dir and args.book_name):
        ap.error("--book-dir 与 --book-name 在 summarize/segment/label/arc/all 阶段必填")

    dbmod.init_db()
    db = dbmod.SessionLocal()
    rate = pi.RateLimiter(args.interval)
    t0 = time.time()

    if args.stage == "anonymize":
        from app.services import anonymizer
        st = anonymizer.anonymize_book(db, args.book_name)
        print(f"[anonymize] {st['aliases']} 条映射，触及 {st['touched']}/{st['chapters']} 章")
        print(f"   主角 -> {st['protagonist']} | 境界阶梯 -> {st['realms']}")
        print(f"[done] {time.time() - t0:.0f}s")
        db.close()
        return 0

    if args.stage == "distill":
        from app.services import plot_distill
        st = plot_distill.distill_all(
            db, book_names=[args.book_name] if args.book_name else None,
            threshold=args.threshold, min_arcs=args.min_arcs)
        print(f"[distill] {st['groups']} 组 → 入库 {st['created']} 个模板（draft 待人工审核）")
        for t in st["templates"]:
            print(f"   · {t['name']}（{t['arcs']} 弧 / {len(t['books'])} 书 / 相似度 {t['avg_sim']}）")
        for f in st["failed"]:
            print(f"   ✗ {f['group']}: {f['reason']}")
        path = plot_distill.export_template_report(db)
        print(f"[report] {path}")
        print(f"[done] {time.time() - t0:.0f}s")
        db.close()
        return 0

    def _prog4(label):
        return lambda no, done, skipped, failed: print(
            f"   {label} 第{no}章 done={done} skip={skipped} fail={failed}", flush=True)

    def _prog2(label):
        return lambda done, total: print(f"   {label} {done}/{total} 章", flush=True)

    if args.stage in ("summarize", "all"):
        if args.batch_summarize > 1 or args.concurrency > 1:
            # 批量 / 并发路径（LLM 在工作线程，DB 写在主线程）
            st = pi.import_chapters_batch(
                db, args.book_dir, args.book_name,
                batch_size=args.batch_summarize, concurrency=args.concurrency,
                start=args.start, end=args.end, rate=rate, progress=_prog4("概括"))
        else:
            # 默认路径：逐章串行（与旧版本行为完全一致）
            st = pi.import_chapters(db, args.book_dir, args.book_name,
                                    start=args.start, end=args.end, rate=rate,
                                    progress=_prog4("概括"))
        print(f"[summarize] {st}")
    if args.stage in ("segment", "all"):
        st = pi.segment_chapters(db, args.book_name, batch=args.batch,
                                 concurrency=args.concurrency, force=args.force,
                                 rate=rate, progress=_prog2("段切分"))
        print(f"[segment] {st}")
    if args.stage in ("label", "all"):
        st = pi.label_segments(db, args.book_name, rate=rate)
        print(f"[label] {st}")
    if args.stage in ("arc", "all"):
        # 故事弧归并：用 DeepSeek V4.1 Flash（升档模型，需 app_configs.llm.deepseek_key）
        st = pi.merge_arcs(db, args.book_name, rate=rate)
        print(f"[arc] {st}")

    path = pi.export_report(db, args.book_name, args.out)
    print(f"[report] {path}")
    print(f"[done] {time.time() - t0:.0f}s")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
