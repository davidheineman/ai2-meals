#!/usr/bin/env python3
"""
Build a meat × lunch-day matrix from csv/mains.csv (binary: did this protein appear that day).

Requires: pip install matplotlib

Other good options (not implemented here):
- Spreadsheet: pivot table with days as columns, meats as rows.
- Observable / Hex notebook: brushable calendar.
- Plotly: same heatmap but zoomable in HTML.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path


def _day_from_filename(name: str) -> date:
    """Parse `01-05.md` → date in year 2026 (menu season for this repo)."""
    stem = Path(name).stem
    month_s, day_s = stem.split("-", 1)
    return date(2026, int(month_s), int(day_s))


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _register_manrope() -> None:
    """Register bundled Manrope so ``font.family: Manrope`` resolves without a system install."""
    from matplotlib import font_manager

    font_path = Path(__file__).resolve().parent / "fonts" / "Manrope-Variable.ttf"
    if font_path.is_file():
        font_manager.fontManager.addfont(str(font_path))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "csv",
        type=Path,
        nargs="?",
        default=None,
        help="Input CSV (default: csv/mains.csv)",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write PNG here (default: plot/mains-heatmap.png)",
    )
    ap.add_argument(
        "--show",
        action="store_true",
        help="Open interactive window instead of writing a PNG",
    )
    args = ap.parse_args()
    try:
        import matplotlib.pyplot as plt
        from matplotlib.colors import ListedColormap
        from matplotlib.patches import Patch
    except ImportError:
        raise SystemExit("Install matplotlib: pip install matplotlib") from None

    # _register_manrope()

    root = Path(__file__).resolve().parent
    csv_path = args.csv or (root / "csv" / "mains.csv")
    rows = _load_rows(csv_path)
    by_day: dict[date, set[str]] = defaultdict(set)
    for r in rows:
        d = _day_from_filename(r["file"])
        m = (r.get("meat") or "").strip()
        if not m:
            m = "(other / unlabeled)"
        by_day[d].add(m)

    days = sorted(by_day.keys())
    meats_seen = set.union(*(by_day[d] for d in days))

    def _days_with(m: str) -> int:
        return sum(1 for d in days if m in by_day[d])

    # Most common labels at the top; tie-break alphabetically (least → bottom among equals).
    meat_rows = sorted(meats_seen, key=lambda m: (-_days_with(m), m))

    data = [[1.0 if m in by_day[d] else 0.0 for d in days] for m in meat_rows]
    labels = [f"{d.month:02d}-{d.day:02d}" for d in days]

    fig_h = max(4, 0.12 * len(meat_rows) + 2)
    fig_w = max(8, 0.08 * len(days) + 3)
    present = "#F0529C"
    absent = "#FAFAFA"
    cmap = ListedColormap([absent, present])

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.imshow(data, aspect="auto", cmap=cmap, vmin=0, vmax=1)
    ax.set_yticks(range(len(meat_rows)), labels=meat_rows)
    step = max(1, len(labels) // 20)
    ax.set_xticks(range(0, len(labels), step))
    ax.set_xticklabels(labels[::step], rotation=45, ha="right", fontsize=8)
    ax.set_xlabel("Day (2026)", fontsize=14)
    ax.set_title("Ai2 Proteins", fontsize=14)
    # Two discrete swatches only (binary matrix — no continuous colorbar).
    legend_handles = [
        Patch(
            facecolor=present,
            edgecolor="#999999",
            linewidth=0.6,
            label="Present",
        ),
        Patch(
            facecolor=absent,
            edgecolor="#999999",
            linewidth=0.6,
            label="Not present",
        ),
    ]
    ax.legend(
        handles=legend_handles,
        loc="lower right",
        frameon=True,
        framealpha=0.95,
    )
    fig.tight_layout()
    if args.show:
        plt.show()
    else:
        out = args.output or (root / "plot" / "mains-heatmap.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=150, bbox_inches="tight")
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
