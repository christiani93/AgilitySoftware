"""
SM-2026 Final-Validierung
=========================
Vollständige Validierung: Lädt Testdaten, berechnet, vergleicht gegen PDFs.
"""
import sys
import re
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("❌ pdfplumber nicht installiert")
    sys.exit(1)

# Relative Pfade für Module
sys.path.insert(0, str(Path(__file__).parent.parent / "web_app"))
from sm_import import parse_sm_result_csv
from sm_final import calculate_sm_final

TEST_ROOT = Path.home() / "OneDrive" / "Agility_Test_20260620" / "tkamo_sm_2026_reference"
QUALI_CSV = TEST_ROOT / "tkamo-results" / "Resultat_Export_Agility_Schweizermeisterschaft_2026_07_11_26_Samstag.csv"
FINAL_CSV = TEST_ROOT / "tkamo-results" / "Resultat_Export_Agility_Schweizermeisterschaft_2026_08_11_26_Sonntag.csv"
RANKING_DIR = TEST_ROOT / "Ranking"

PDF_MAPPING = {
    "Large": "Kombinierte_Ranglisten_über_die_Resultate_Final_Jumping_Large_Final_Agility_Large.pdf",
    "Intermediate": "Kombinierte_Ranglisten_über_die_Resultate_Final_Agility_Intermediate_Final_Jumping_Intermediate.pdf",
    "Medium": "Kombinierte_Ranglisten_über_die_Resultate_Final_Jumping_Medium_Final_Agility_Medium.pdf",
    "Small": "Kombinierte_Ranglisten_über_die_Resultate_Final_Jumping_Small_Final_Agility_Small.pdf",
}


def load_csv(path: Path) -> bytes:
    """Lädt CSV als Bytes."""
    with open(path, "rb") as f:
        return f.read()


def normalize_run_entries(runs: list) -> list:
    """Normalisiert Entry-Struktur nach CSV-Import."""
    for run in runs:
        for entry in run.get("entries", []):
            res = entry.pop("result", {})
            entry["fehler_total"] = (res.get("fehler") or 0) + (res.get("verweigerungen") or 0)
            entry["fehler_parcours"] = res.get("fehler") or 0
            entry["zeit_total"] = res.get("zeit") or 0
            entry["disqualifikation"] = res.get("disqualifikation") or ""
            entry["platz"] = None
    return runs


def extract_pdf_ranking(pdf_path: Path) -> list:
    """Extrahiert Top-Lizenzen aus PDF."""
    entries = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        lines = text.split("\n")
        for line in lines:
            match = re.match(r"^(\d+)\s+(\d+)\s+(\d+)\s+(.+?)$", line.strip())
            if not match:
                continue

            rang, start_nr, lic, rest = match.groups()
            entries.append({
                "rang": int(rang),
                "lic": lic,
            })
    except Exception as e:
        print(f"  ⚠ PDF-Parse-Fehler: {e}")

    return sorted(entries, key=lambda e: e.get("rang", 9999))


def compare_category(category: str, calculated: list) -> bool:
    """Vergleicht Kategorie: berechnet vs. PDF."""
    print(f"\n{'='*80}")
    print(f"  {category}")
    print(f"{'='*80}")

    pdf_file = PDF_MAPPING.get(category)
    pdf_path = RANKING_DIR / pdf_file if pdf_file else None

    if not pdf_path or not pdf_path.exists():
        print(f"  ❌ PDF nicht gefunden")
        return False

    print(f"\n  📄 Lese PDF: {pdf_file}")
    pdf_entries = extract_pdf_ranking(pdf_path)
    print(f"     ✓ {len(pdf_entries)} Einträge")

    print(f"  🧮 Berechnet: {len(calculated)} Einträge")

    limit = min(5, len(calculated), len(pdf_entries))
    print(f"\n  Top {limit} Lizenzen-Vergleich:")
    print(f"  {'Pos':<4} {'Berechnet':<15} {'PDF':<15} {'Status':<8}")
    print(f"  {'-'*4} {'-'*15} {'-'*15} {'-'*8}")

    matches = 0
    for i in range(limit):
        calc_lic = calculated[i].get("license", "—") if i < len(calculated) else "—"
        pdf_lic = pdf_entries[i].get("lic", "—") if i < len(pdf_entries) else "—"
        match = "✅" if calc_lic == pdf_lic else "❌"
        if match == "✅":
            matches += 1
        print(f"  {i+1:<4} {calc_lic:<15} {pdf_lic:<15} {match:<8}")

    result = matches == limit
    status = "✅ GRÜN" if result else f"⚠️  {matches}/{limit}"
    print(f"\n  {status}\n")

    return result


def main():
    print("\n🔍 SM-2026 Final-Validierung")
    print(f"   Berechnung + PDF-Vergleich")

    # Lade Daten
    print("\n📥 Lade CSV-Exporte...")
    try:
        quali_data = load_csv(QUALI_CSV)
        quali_runs = parse_sm_result_csv(quali_data, "quali")
        quali_runs = normalize_run_entries(quali_runs)

        final_data = load_csv(FINAL_CSV)
        final_runs = parse_sm_result_csv(final_data, "final")
        final_runs = normalize_run_entries(final_runs)
        print(f"   ✓ {len(quali_runs)} Quali-Läufe, {len(final_runs)} Final-Läufe")
    except Exception as e:
        print(f"   ✗ Fehler: {e}")
        return 1

    # Berechne
    print("\n⚙️  Berechne SM-Final...")
    try:
        event = {"id": "SM_2026", "runs": quali_runs + final_runs}
        result = calculate_sm_final(event)
        print(f"   ✓ {len(result)} Kategorien")
    except Exception as e:
        print(f"   ✗ Fehler: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Vergleiche
    print("\n📊 PDF-Vergleich:")
    all_ok = True
    for cat in ["Large", "Intermediate", "Medium", "Small"]:
        cat_data = result.get(cat, {})
        combined = cat_data.get("combined", [])
        if not compare_category(cat, combined):
            all_ok = False

    # Ergebnis
    print(f"{'='*80}")
    if all_ok:
        print("  ✅ ALLE KATEGORIEN GRÜN")
    else:
        print("  ⚠️  EINIGE ABWEICHUNGEN")
    print(f"{'='*80}\n")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
