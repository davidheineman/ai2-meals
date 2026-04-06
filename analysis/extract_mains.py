#!/usr/bin/env python3
"""Extract Mains section entries from `data/*.md` and infer a primary protein label."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

# Collapsed label for Friday "build your sandwich" menus (many breads, cheeses, fixings).
SANDWICH_MEAT_LABEL = "sandwich meat"
SANDWICH_BAR_MAIN_NAME = "Sandwich bar"

MAIN_LINE = re.compile(r"^-\s+\*\*(.+?)\*\*(?:\s*\([^)]*\))?\s*$")
ING_LINE = re.compile(r"^  -\s+(.+)$")
HEADER_DATE = re.compile(r"^#\s+.+\s+—\s+(.+)$")


def _norm_main_key(name: str) -> str:
    return " ".join(name.strip().upper().split())


# Exact dish title → meat label (overrides generic title heuristics).
_SPECIAL_MAIN_MEAT: dict[str, str] = {
    _norm_main_key("GYRO SPICED ROASTED CAULIFLOWER AND CHICKPEA"): "cauliflower",
    _norm_main_key("DJAN THAI VEGETABLE DELIGHT"): "vegetable",
    _norm_main_key("PERUVIAN-STYLE MARINATED CHICKPEA AND MUSHROOM"): "chickpea",
    _norm_main_key("CAULIFLOWER WITH SMOKY PAPRIKA, CHICKPEAS, AND TOMATO"): "tomato",
    _norm_main_key("VEGGIE BOLOGNESE"): "vegetable",
}

_SKIP_MAIN_SUBSTRINGS: tuple[str, ...] = ("SALAD", "DRESSING", "VINAIGRETTE")


def _skip_salad_dressing_vinaigrette(main_name: str) -> bool:
    u = main_name.upper()
    return any(s in u for s in _SKIP_MAIN_SUBSTRINGS)

# Order matters: more specific / longer phrases first.
_TITLE_PROTEIN: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bPLANT[- ]BASED\b", re.I), "plant-based"),
    (re.compile(r"\bIMPOSSIBLE\b", re.I), "plant-based"),
    (re.compile(r"\bBEYOND\b", re.I), "plant-based"),
    (re.compile(r"\bHALIBUT\b", re.I), "halibut"),
    (re.compile(r"\bSALMON\b", re.I), "salmon"),
    (re.compile(r"\bCOD\b", re.I), "cod"),
    (re.compile(r"\bSHRIMP\b", re.I), "shrimp"),
    (re.compile(r"\bCHICKEN\b", re.I), "chicken"),
    (re.compile(r"\bTURKEY\b", re.I), "turkey"),
    (re.compile(r"\bDUCK\b", re.I), "duck"),
    (re.compile(r"\bPORK\b", re.I), "pork"),
    (re.compile(r"\bBACON\b", re.I), "pork"),
    (re.compile(r"\bHAM\b", re.I), "pork"),
    (re.compile(r"\bLAMB\b", re.I), "lamb"),
    (re.compile(r"\bPASTRAMI\b", re.I), "pastrami"),
    (re.compile(r"\bBEEF\b", re.I), "beef"),
    (re.compile(r"\bSTEAK\b", re.I), "beef"),
    (re.compile(r"\bFLANK\b", re.I), "beef"),
    (re.compile(r"\bLOMO\b", re.I), "beef"),
    (re.compile(r"\bTOFU\b", re.I), "tofu"),
    (re.compile(r"\bTEMPEH\b", re.I), "tempeh"),
    (re.compile(r"\bPANEER\b", re.I), "paneer"),
    (re.compile(r"\bSOY CURLS?\b", re.I), "soy curls"),
    (re.compile(r"\bFALAFEL\b", re.I), "chickpea"),
    (re.compile(r"\bCHICKPEAS?\b", re.I), "chickpea"),
    (re.compile(r"\bJACKFRUIT\b", re.I), "jackfruit"),
    (re.compile(r"\bCAULIFLOWER\b", re.I), "cauliflower"),
    (re.compile(r"\bMUSHROOMS?\b", re.I), "mushrooms"),
]

# First comma-separated clause of ingredients (often the primary protein).
_CHUNK_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"plant[- ]based", re.I), "plant-based"),
    (re.compile(r"\bhalal\s+chicken\b", re.I), "chicken"),
    (re.compile(r"\bchicken\b", re.I), "chicken"),
    (re.compile(r"\bgrilled\s+tofu\b", re.I), "tofu"),
    (re.compile(r"\btofu\b", re.I), "tofu"),
    (re.compile(r"\btempeh\b", re.I), "tempeh"),
    (re.compile(r"\bpork\b", re.I), "pork"),
    (re.compile(r"\bbeef\b", re.I), "beef"),
    (re.compile(r"\bhalibut\b", re.I), "halibut"),
    (re.compile(r"\bsalmon\b", re.I), "salmon"),
    (re.compile(r"\bcod\b", re.I), "cod"),
    (re.compile(r"\bshrimp\b", re.I), "shrimp"),
    (re.compile(r"\bfalafel\b", re.I), "chickpea"),
    (re.compile(r"\bchickpeas?\b", re.I), "chickpea"),
    (re.compile(r"\bjackfruit\b", re.I), "jackfruit"),
    (re.compile(r"\bcauliflower\b", re.I), "cauliflower"),
    (re.compile(r"\bmushrooms?\b", re.I), "mushrooms"),
    (re.compile(r"\blamb\b", re.I), "lamb"),
    (re.compile(r"\bturkey\b", re.I), "turkey"),
    (re.compile(r"\bduck\b", re.I), "duck"),
    (re.compile(r"(?<!vegan )\bfish\b(?!\s+sauce)", re.I), "fish"),
]


def _menu_date(lines: list[str]) -> str:
    for line in lines:
        m = HEADER_DATE.match(line.strip())
        if m:
            return m.group(1).strip()
    return ""


def _parse_mains_block(lines: list[str]) -> list[tuple[str, str]]:
    """Return (dish name, ingredients text or '')."""
    out: list[tuple[str, str]] = []
    in_mains = False
    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")
        if line.startswith("### "):
            title = line[4:].strip()
            if title == "Mains":
                in_mains = True
            elif in_mains:
                break
            i += 1
            continue
        if not in_mains:
            i += 1
            continue
        m = MAIN_LINE.match(line)
        if m:
            name = m.group(1).strip()
            ingredients = ""
            if i + 1 < len(lines):
                im = ING_LINE.match(lines[i + 1].rstrip("\n"))
                if im:
                    ingredients = im.group(1).strip()
                    i += 1
            out.append((name, ingredients))
        i += 1
    return out


def infer_meat(main_name: str, ingredients: str) -> str:
    special = _SPECIAL_MAIN_MEAT.get(_norm_main_key(main_name))
    if special:
        return special
    for pat, label in _TITLE_PROTEIN:
        if pat.search(main_name):
            return label
    first = ingredients.split(",")[0] if ingredients else ""
    for pat, label in _CHUNK_PATTERNS:
        if pat.search(first):
            return label
    low = ingredients.lower() if ingredients else ""
    for pat, label in _CHUNK_PATTERNS:
        if pat.search(low):
            return label
    return ""


def file_sort_key(p: Path) -> tuple[int, int]:
    stem = p.stem
    try:
        month, day = stem.split("-", 1)
        return int(month), int(day)
    except ValueError:
        return 0, 0


def _is_friday_sandwich_bar(menu_date: str, mains: list[tuple[str, str]]) -> bool:
    """Long Friday Mains with multiple Macrina bread lines — sandwich assembly, not separate entrées."""
    if "FRIDAY" not in menu_date.upper():
        return False
    return _is_sandwich_assembly_mains(mains)


def _is_sandwich_assembly_mains(mains: list[tuple[str, str]]) -> bool:
    """Mains is a build-your-own sandwich lineup (multiple Macrina breads + fillings)."""
    if len(mains) < 10:
        return False
    macrina = sum(1 for name, _ in mains if "MACRINA" in name.upper())
    return macrina >= 2


_SANDWICH_FIXING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"MACRINA", re.I),
    re.compile(r"^LETTUCE$", re.I),
    re.compile(r"^TOMATO$", re.I),
    re.compile(r"^RED ONION$", re.I),
    re.compile(r"CHEESE\b", re.I),
    re.compile(r"\bPICKLE", re.I),
    re.compile(r"BRITT'?S", re.I),
    re.compile(r"PANGEA FERMENTS", re.I),
    re.compile(r"SAUERKRAUT", re.I),
    re.compile(r"MAMA LIL", re.I),
    re.compile(r"CHIMICHURRI", re.I),
    re.compile(r"AIOLI", re.I),
    re.compile(r"MAYONNAISE", re.I),
)


def _is_sandwich_fixing(main_name: str) -> bool:
    return any(p.search(main_name) for p in _SANDWICH_FIXING_PATTERNS)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--data",
        type=Path,
        default=None,
        help="Markdown directory (default: <repo>/data)",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write CSV here (default: csv/mains.csv)",
    )
    ap.add_argument(
        "--stdout",
        action="store_true",
        help="Write CSV to stdout instead of a file",
    )
    args = ap.parse_args()
    root = Path(__file__).resolve().parent
    data_dir = args.data or root / "data"
    if not data_dir.is_dir():
        print(f"Missing directory: {data_dir}", file=sys.stderr)
        sys.exit(1)
    rows: list[dict[str, str]] = []
    for path in sorted(data_dir.glob("*.md"), key=file_sort_key):
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        menu_date = _menu_date(lines)
        mains = _parse_mains_block(lines)
        if _is_friday_sandwich_bar(menu_date, mains):
            rows.append(
                {
                    "file": path.name,
                    "menu_date": menu_date,
                    "main_name": SANDWICH_BAR_MAIN_NAME,
                    "meat": SANDWICH_MEAT_LABEL,
                }
            )
            continue
        assembly = _is_sandwich_assembly_mains(mains)
        for main_name, ingredients in mains:
            if assembly and _is_sandwich_fixing(main_name):
                continue
            if _skip_salad_dressing_vinaigrette(main_name):
                continue
            rows.append(
                {
                    "file": path.name,
                    "menu_date": menu_date,
                    "main_name": main_name,
                    "meat": infer_meat(main_name, ingredients),
                }
            )
    fieldnames = ["file", "menu_date", "main_name", "meat"]
    if args.stdout:
        w = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    else:
        out = args.output or (root / "csv" / "mains.csv")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote {len(rows)} rows to {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
