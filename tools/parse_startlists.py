"""Parser für die 3 PDF-Startlisten der Aaretaler-Veranstaltung 20.06.2026.

Input: Text-Extrakte (pdftotext -layout) der 3 PDF-Startlisten in /tmp/.
Output: JSON unter web_app/data/test_data/aaretaler_startlists.json mit Struktur:
  {
    "event_name": "...",
    "event_date": "...",
    "classes": {
      "1": {"Small": [{snr, name, license, hund, rasse}, ...], "Medium": ..., ...},
      "2": {...},
      "3": {...},
    }
  }

Reihenfolge im PDF: Small → Medium → Intermediate → Large (Annahme).
"""
import json
import os
import re
import sys
from pathlib import Path

CATEGORIES_ORDER = ["Small", "Medium", "Intermediate", "Large"]

LINE_RE = re.compile(
    r"^\s*(\d+)\s+(.+?)\s+(A\s*J\s*[-S])\s+([A-Z]{3})\s+(\d+)\s*(.*)$"
)
STARTER_RE = re.compile(r"Starter:\s*(\d+)")


def parse_pdf_text(path: Path) -> tuple[list, list[int]]:
    rows = []
    starter_counts = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        m_st = STARTER_RE.search(line)
        if m_st:
            starter_counts.append(int(m_st.group(1)))
            continue
        m = LINE_RE.match(line)
        if m:
            snr = int(m.group(1))
            name = re.sub(r"\s+", " ", m.group(2).strip())
            land = m.group(4)
            lizenz_nr = m.group(5)
            rest = m.group(6).strip()
            hund, rasse = "", ""
            if rest:
                parts = re.split(r"\s{2,}", rest)
                hund = parts[0].strip()
                rasse = parts[1].strip() if len(parts) > 1 else ""
            rows.append({
                "snr":     snr,
                "name":    name,
                "land":    land,
                "lizenz":  lizenz_nr,
                "hund":    hund,
                "rasse":   rasse,
            })
    return rows, starter_counts


def assign_categories(rows: list, starter_counts: list[int]) -> dict:
    result: dict[str, list] = {c: [] for c in CATEGORIES_ORDER}
    if not rows:
        return result
    if len(starter_counts) == len(CATEGORIES_ORDER):
        idx = 0
        for cat, count in zip(CATEGORIES_ORDER, starter_counts):
            result[cat] = rows[idx:idx + count]
            idx += count
        if idx < len(rows):
            result["Large"].extend(rows[idx:])
    elif len(starter_counts) > 0:
        cat_idx = 0
        row_idx = 0
        for count in starter_counts:
            cat = CATEGORIES_ORDER[min(cat_idx, len(CATEGORIES_ORDER) - 1)]
            result[cat].extend(rows[row_idx:row_idx + count])
            row_idx += count
            cat_idx += 1
        if row_idx < len(rows):
            result["Large"].extend(rows[row_idx:])
    else:
        result["Large"] = rows
    return result


def main():
    base = Path(os.environ.get("TEMP") or "/tmp")
    files = {
        "1": base / "20260619T151824_1_2026-06-20_Startlist_Class1.txt",
        "2": base / "20260619T151824_0_2026-06-20_Startlist_Class2.txt",
        "3": base / "20260619T151824_2_2026-06-20_Startlist_Class3.txt",
    }
    classes = {}
    for klasse, fp in files.items():
        if not fp.exists():
            print(f"FEHLT: {fp}", file=sys.stderr)
            continue
        rows, starter_counts = parse_pdf_text(fp)
        by_cat = assign_categories(rows, starter_counts)
        classes[klasse] = by_cat
        sums = {c: len(by_cat[c]) for c in CATEGORIES_ORDER}
        print(f"Klasse {klasse}: parsed={len(rows)}, starter_counts={starter_counts}, "
              f"assigned={sums}, total={sum(sums.values())}")

    out = {
        "event_name":     "SWISS AGILITY SUMMITS & Aaretaler Hundesport",
        "event_date":     "2026-06-20",
        "event_location": "3110 Münsingen",
        "classes":        classes,
    }
    out_dir = Path(__file__).parent.parent / "web_app" / "data" / "test_data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "aaretaler_startlists.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
