#!/usr/bin/env python3
"""
Transition counts for Mains whose inferred ``meat`` is neither chicken nor a
vegetarian / meatless protein label (see ``_VEGETARIAN_MEATS``).

By default, counts include (1) consecutive pairs on the same menu day and (2)
from the last filtered main of one day to the first filtered main of the next
calendar day (files sorted by ``MM-DD.md``).

Use ``--within-day-only`` to restrict to same-day pairs only.

Writes a directed-graph PNG (via Graphviz ``dot``) and optional CSV of counts.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path


# Meatless / vegetarian proteins and sides we treat as "vegetarian" for this filter.
_VEGETARIAN_MEATS: frozenset[str] = frozenset(
    {
        "tofu",
        "tempeh",
        "plant-based",
        "chickpea",
        "mushrooms",
        "cauliflower",
        "jackfruit",
        "paneer",
        "soy curls",
        "vegetable",
        "tomato",
    }
)


def _keep_meat(meat: str) -> bool:
    m = (meat or "").strip().lower()
    if not m or m == "chicken":
        return False
    if m in _VEGETARIAN_MEATS:
        return False
    return True


def _load_grouped(path: Path) -> dict[str, list[str]]:
    """file stem -> ordered list of meat labels (as stored in CSV)."""
    by_file: dict[str, list[str]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            by_file[row["file"]].append((row.get("meat") or "").strip())
    return by_file


def _transitions(
    grouped: dict[str, list[str]], *, cross_day: bool = True
) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    files = sorted(grouped.keys())
    for file in files:
        seq = [m for m in grouped[file] if _keep_meat(m)]
        for a, b in zip(seq, seq[1:]):
            counts[(a, b)] += 1
    if cross_day:
        for f0, f1 in zip(files, files[1:]):
            s0 = [m for m in grouped[f0] if _keep_meat(m)]
            s1 = [m for m in grouped[f1] if _keep_meat(m)]
            if s0 and s1:
                counts[(s0[-1], s1[0])] += 1
    return counts


def _square_matrix(labels: list[str], counts: Counter[tuple[str, str]]) -> list[list[int]]:
    idx = {lb: i for i, lb in enumerate(labels)}
    n = len(labels)
    mat = [[0 for _ in range(n)] for _ in range(n)]
    for (a, b), c in counts.items():
        if a in idx and b in idx:
            mat[idx[a]][idx[b]] += c
    return mat


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
        "--plot-dir",
        type=Path,
        default=None,
        help="Directory for PNG (default: <repo>/plot)",
    )
    ap.add_argument(
        "--csv-out",
        type=Path,
        default=None,
        help="Write transition counts as CSV (optional)",
    )
    ap.add_argument(
        "--no-plot",
        action="store_true",
        help="Skip matplotlib output",
    )
    ap.add_argument(
        "--within-day-only",
        action="store_true",
        help="Do not add last→first transitions across consecutive menu days",
    )
    args = ap.parse_args()
    repo = Path(__file__).resolve().parent.parent
    csv_path = args.csv or (repo / "csv" / "mains.csv")
    if not csv_path.is_file():
        raise SystemExit(f"Missing CSV: {csv_path}")

    grouped = _load_grouped(csv_path)
    counts = _transitions(grouped, cross_day=not args.within_day_only)
    labels = sorted({a for a, _ in counts.keys()} | {b for _, b in counts.keys()})
    mat = _square_matrix(labels, counts)

    if args.csv_out:
        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_out.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["from", "to", "count"])
            for i, a in enumerate(labels):
                for j, b in enumerate(labels):
                    c = mat[i][j]
                    if c:
                        w.writerow([a, b, c])
        print(f"Wrote {args.csv_out}", flush=True)

    if args.no_plot:
        return

    if not shutil.which("dot"):
        raise SystemExit("Graphviz `dot` not found — install via `brew install graphviz`")

    plot_dir = args.plot_dir or (repo / "plot")
    plot_dir.mkdir(parents=True, exist_ok=True)
    png_path = plot_dir / "meat-transitions.png"

    total = sum(counts.values()) or 1
    weights = {edge: c / total for edge, c in counts.items()}
    max_w = max(weights.values()) if weights else 1.0

    # How often each meat appears (fraction of all filtered main slots).
    occur: Counter[str] = Counter()
    for file in sorted(grouped.keys()):
        for m in grouped[file]:
            if _keep_meat(m):
                occur[m] += 1
    total_occur = sum(occur.values()) or 1
    occur_frac = {m: occur[m] / total_occur for m in labels}

    # Node size proportional to occurrence frequency.
    max_of = max(occur_frac.values()) if occur_frac else 1.0

    AI2_TEAL = (0x10, 0x52, 0x57)
    AI2_PINK = (0xF0, 0x52, 0x9C)
    AI2_PURPLE = (0xB1, 0x1B, 0xE8)

    def _hex(rgb: tuple[int, int, int]) -> str:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> str:
        return _hex(tuple(int(ac + (bc - ac) * t) for ac, bc in zip(a, b)))  # type: ignore[arg-type]

    # Nodes: light teal wash → full teal by importance.
    # Edges: pink → purple gradient by weight.

    dot_lines = [
        "digraph meat_transitions {",
        "  graph [",
        '    layout=neato, overlap=false, splines=curved,',
        '    bgcolor="white", pad="0.3,0.2",',
        f'    label="Non-chicken, Non-veg Ai2 Meat Transition Matrix",',
        f'    labelloc=t, fontsize=24, fontname="Helvetica Neue Bold", fontcolor="{_hex(AI2_TEAL)}",',
        "  ];",
        "  node [",
        f'    shape=circle, style=filled, fontname="Helvetica Neue Bold",',
        f'    fontsize=15, color="{_hex(AI2_TEAL)}", fontcolor="white", penwidth=2.5,',
        "  ];",
        "  edge [",
        f'    fontname="Helvetica Neue", fontsize=12, fontcolor="{_hex(AI2_PURPLE)}",',
        "  ];",
    ]

    for label in labels:
        t = occur_frac.get(label, 0) / max_of
        w = 1.1 + 0.7 * t
        fill = _lerp((0xA8, 0xD8, 0xDB), AI2_TEAL, 0.25 + 0.75 * t)
        of = occur_frac.get(label, 0)
        pct = f"{of:.0%}" if of >= 0.095 else f"{of:.1%}"
        dot_lines.append(
            f'  "{label}" [label="{label}\\n{pct}", fillcolor="{fill}", width={w:.2f}];'
        )

    for (a, b), w in sorted(weights.items(), key=lambda kv: kv[1]):
        t = w / max_w
        pen = 1.2 + 5.0 * t
        color = _lerp(AI2_PINK, AI2_PURPLE, t)
        pct = f"{w:.0%}" if w >= 0.095 else f"{w:.1%}"
        dot_lines.append(
            f'  "{a}" -> "{b}" '
            f'[label="  {pct}", penwidth={pen:.1f}, color="{color}cc"];'
        )

    dot_lines.append("}")
    dot_src = "\n".join(dot_lines) + "\n"

    with tempfile.NamedTemporaryFile(suffix=".dot", mode="w", delete=False) as tmp:
        tmp.write(dot_src)
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["dot", "-Kneato", "-Tpng", "-Gdpi=200", "-o", str(png_path), tmp_path],
            check=True,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    print(f"Wrote {png_path}", flush=True)


if __name__ == "__main__":
    main()
