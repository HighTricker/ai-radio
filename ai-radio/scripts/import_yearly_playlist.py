"""年度歌单导入 CLI

用法：
    # 从文件导入
    python scripts/import_yearly_playlist.py --source "QQ 音乐 2025" --file my_yearly.txt

    # 从 stdin 导入（适合粘贴）
    python scripts/import_yearly_playlist.py --source "QQ 音乐 2025" --stdin

    # 只解析不写入（验证格式）
    python scripts/import_yearly_playlist.py --source "QQ 音乐 2025" --file my_yearly.txt --dry-run

输入文件格式：
    每行一首歌。支持多种格式：
      夜空中最亮的星 - 逃跑计划
      1. 富士山下 - 陈奕迅
      🎵 [VIP] 山丘 - 李宗盛
      晴天（周杰伦）

工作机制：
    与现有 data/user/taste.md 去重合并，新条目按 ## 来源标签 分组追加到末尾。
    playlist.py 解析时跳过 # 行，所以分组标题不影响后端读取。
"""
import argparse
import sys
from pathlib import Path

# Windows console 默认 GBK，强制 stdout 为 UTF-8 让 emoji / 中文都正常输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# 让脚本能 from services.* import：把 backend 加到 sys.path
ROOT = Path(__file__).resolve().parent.parent  # ai-radio/
sys.path.insert(0, str(ROOT / "backend"))

from services.playlist_importer import merge_into_taste, parse_playlist_text  # noqa: E402


def _read_input(args: argparse.Namespace) -> str:
    if args.file:
        path = Path(args.file)
        if not path.exists():
            sys.exit(f"❌ 文件不存在：{path}")
        return path.read_text(encoding="utf-8")
    if args.stdin:
        return sys.stdin.read()
    sys.exit("❌ 必须指定 --file 或 --stdin")


def _preview(entries: list, n: int = 10) -> None:
    for i, e in enumerate(entries[:n], 1):
        print(f"  {i:2d}. {e.display}")
    if len(entries) > n:
        print(f"  ...（其余 {len(entries) - n} 首省略）")


def main() -> None:
    p = argparse.ArgumentParser(
        description="年度歌单导入到 taste.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--source", required=True, help="来源标签，写入 taste.md 的分组标题，如 'QQ 音乐 2025'")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--file", help="读取的文本文件路径（UTF-8）")
    grp.add_argument("--stdin", action="store_true", help="从 stdin 读取")
    p.add_argument("--dry-run", action="store_true", help="只解析+预览，不写入 taste.md")
    args = p.parse_args()

    raw_text = _read_input(args)
    entries = parse_playlist_text(raw_text)

    if not entries:
        sys.exit("❌ 没有解析出任何歌曲。请检查输入格式（每行 '歌名 - 歌手'）。")

    print(f"✅ 解析出 {len(entries)} 首：")
    _preview(entries)

    added, skipped = merge_into_taste(entries, args.source, dry_run=args.dry_run)

    if args.dry_run:
        print(f"\n[dry-run] 会写入 {len(added)} 首，跳过已存在 {skipped} 首。未实际修改 taste.md。")
        return

    print(f"\n✅ 已合并到 taste.md：")
    print(f"   · 来源分组：## {args.source}")
    print(f"   · 新增：{len(added)} 首")
    print(f"   · 跳过（已存在）：{skipped} 首")


if __name__ == "__main__":
    main()
