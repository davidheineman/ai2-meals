#!/usr/bin/env python3
"""Convert saved Café Bon Appétit / Ai2 lunch HTML emails to compact Markdown."""

from __future__ import annotations

import argparse
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup


@dataclass
class MenuItem:
    name: str
    diet: list[str]
    station: str
    description: str


ZW_SPACE_CHARS = frozenset(
    ch
    for ch in map(chr, range(0x200B, 0x2010))
    if unicodedata.category(ch) in ("Cf", "Zs")
)


def norm(s: str) -> str:
    t = s.translate({ord(c): None for c in ZW_SPACE_CHARS})
    t = " ".join(t.split())
    return t.strip()


def _style(el) -> str:
    return (el.get("style") or "").replace(" ", "").lower()


def extract_date(soup: BeautifulSoup) -> str:
    for div in soup.find_all("div"):
        st = _style(div)
        if "font-size:18px" in st and "font-weight:600" in st:
            t = norm(div.get_text())
            if t:
                return t
    if soup.title and soup.title.string:
        return norm(soup.title.string)
    return "Unknown date"


def extract_featured(soup: BeautifulSoup) -> tuple[str, str] | None:
    h2 = soup.find("h2")
    if not h2:
        return None
    title = norm(h2.get_text())
    blurb = ""
    nxt = h2.find_next_sibling("div")
    if nxt:
        p = nxt.find("p")
        if p:
            blurb = norm(p.get_text())
        else:
            blurb = norm(nxt.get_text())
    if not title and not blurb:
        return None
    return title, blurb


def extract_cafe_and_hours(soup: BeautifulSoup) -> tuple[str, str]:
    cafe = "Ai2"
    hours = ""
    for td in soup.find_all("td"):
        st = _style(td)
        if "#4f4c4d" in st and "uppercase" in st:
            t = norm(td.get_text())
            if t and len(t) < 40:
                cafe = t
        if "#6f6c6d" in st and ("am" in td.get_text().lower() or "pm" in td.get_text().lower()):
            hours = norm(td.get_text())
    return cafe, hours


def _diet_from_imgs(meta_span) -> list[str]:
    tags: list[str] = []
    if not meta_span:
        return tags
    for img in meta_span.find_all("img"):
        alt = (img.get("alt") or "").strip()
        if not alt or alt.endswith(" Icon"):
            continue
        tags.append(alt)
    return tags


def _station_from_meta(meta_span) -> str:
    if not meta_span:
        return ""
    # Inner span holds "Salad Bar", etc.; get_text collapses @ and station.
    t = norm(meta_span.get_text())
    t = t.lstrip("@").strip()
    return t


def _description_from_dish_span(dish_span) -> str:
    table = dish_span.find_parent("table")
    if not table:
        return ""
    tbody = table.find("tbody", recursive=False)
    if not tbody:
        return ""
    rows = tbody.find_all("tr", recursive=False)
    if len(rows) < 2:
        return ""
    desc_td = rows[1].find("td")
    if not desc_td:
        return ""
    return norm(desc_td.get_text())


def extract_menu_items(soup: BeautifulSoup) -> list[MenuItem]:
    items: list[MenuItem] = []
    for span in soup.find_all("span"):
        st = _style(span)
        if "font-size:19px" not in st or "font-weight:700" not in st:
            continue
        name = norm(span.get_text())
        if not name or name.upper() == "LUNCH":
            continue
        meta = span.find_next_sibling("span")
        if meta and "font-size:14px" not in _style(meta):
            meta = None
        station = _station_from_meta(meta)
        diet = _diet_from_imgs(meta)
        desc = _description_from_dish_span(span)
        if desc.lower() == name.lower():
            desc = ""
        items.append(MenuItem(name=name, diet=diet, station=station, description=desc))
    return items


def items_by_station(items: list[MenuItem]) -> dict[str, list[MenuItem]]:
    buckets: dict[str, list[MenuItem]] = defaultdict(list)
    order: list[str] = []
    for it in items:
        key = it.station or "Other"
        if key not in buckets:
            order.append(key)
        buckets[key].append(it)
    return {k: buckets[k] for k in order}


def to_markdown(
    date: str,
    cafe: str,
    hours: str,
    featured: tuple[str, str] | None,
    items: list[MenuItem],
) -> str:
    lines: list[str] = [f"# {cafe} lunch — {date}"]
    if hours:
        lines.append(f"**Hours:** {hours}")
    lines.append("")
    if featured:
        title, blurb = featured
        lines.append("## Featured")
        lines.append(f"**{title}**")
        if blurb:
            lines.append(blurb)
        lines.append("")
    lines.append("## Menu")
    lines.append("")
    for station, group in items_by_station(items).items():
        lines.append(f"### {station}")
        for it in group:
            diet_suffix = ""
            if it.diet:
                diet_suffix = " (" + ", ".join(it.diet) + ")"
            lines.append(f"- **{it.name}**{diet_suffix}")
            if it.description:
                lines.append(f"  - {it.description}")
        lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def html_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    date = extract_date(soup)
    cafe, hours = extract_cafe_and_hours(soup)
    featured = extract_featured(soup)
    items = extract_menu_items(soup)
    return to_markdown(date, cafe, hours, featured, items)


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert Ai2 meal HTML to Markdown.")
    ap.add_argument("path", type=Path, help="Path to saved .html file")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write Markdown here (default: print to stdout)",
    )
    args = ap.parse_args()
    text = args.path.read_text(encoding="utf-8", errors="replace")
    md = html_to_markdown(text)
    if args.output:
        args.output.write_text(md + "\n", encoding="utf-8")
    else:
        sys.stdout.write(md + "\n")


if __name__ == "__main__":
    main()
