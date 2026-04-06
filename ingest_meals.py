#!/usr/bin/env python3
"""Convert every `raw/*.html` file to `data/<name>.md`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from meal_to_md import html_to_markdown


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--raw",
        type=Path,
        default=None,
        help="Source directory (default: <repo>/raw)",
    )
    ap.add_argument(
        "--data",
        type=Path,
        default=None,
        help="Output directory (default: <repo>/data)",
    )
    args = ap.parse_args()
    root = Path(__file__).resolve().parent
    raw_dir = args.raw or root / "raw"
    data_dir = args.data or root / "data"
    if not raw_dir.is_dir():
        print(f"Missing directory: {raw_dir}", file=sys.stderr)
        sys.exit(1)
    paths = sorted(raw_dir.glob("*.html"))
    if not paths:
        print(f"No .html files in {raw_dir}", file=sys.stderr)
        sys.exit(1)
    data_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        md = html_to_markdown(path.read_text(encoding="utf-8", errors="replace"))
        out = data_dir / f"{path.stem}.md"
        out.write_text(md + "\n", encoding="utf-8")
        print(out)


if __name__ == "__main__":
    main()
