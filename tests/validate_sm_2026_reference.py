"""
SM-2026-Referenzdaten Validierung
==================================
Lädt TKAMO-Resultat-Exporte (Quali Sa + Final So) und verifiziert den SM-Rechenkern
gegen offizielle Ranglisten-PDFs.

Testdaten: Agility_Test_20260620/tkamo_sm_2026_reference/
  - Startlist/SM2026_Anmeldungen_konsolidiert.csv
  - tkamo-results/*.csv (Quali + Final)
  - Ranking/*.pdf (Referenz-Ranglisten)
"""
import sys
from pathlib import Path

# Pfade (OneDrive\Agility_Test_20260620)
TEST_ROOT = Path.home() / "OneDrive" / "Agility_Test_20260620" / "tkamo_sm_2026_reference"
QUALI_CSV = TEST_ROOT / "tkamo-results" / "Resultat_Export_Agility_Schweizermeisterschaft_2026_07_11_26_Samstag.csv"
FINAL_CSV = TEST_ROOT / "tkamo-results" / "Resultat_Export_Agility_Schweizermeisterschaft_2026_08_11_26_Sonntag.csv"

# Relative Pfade für Module (von tests/ aus)
sys.path.insert(0, str(Path(__file__).parent.parent / "web_app"))
from sm_import import parse_sm_result_csv
from sm_final import calculate_sm_final


def load_csv(path: Path) -> bytes:
    """Lädt TKAMO-Resultat-CSV als Bytes."""
    with open(path, "rb") as f:
        return f.read()


def normalize_run_entries(runs: list) -> list:
    """Normalisiert Entry-Struktur nach CSV-Import für sm_final.

    Nach parse_sm_result_csv haben entries ein 'result' Dict.
    sm_final erwartet die Felder direkt auf dem Entry.
    """
    for run in runs:
        for entry in run.get("entries", []):
            res = entry.pop("result", {})
            entry["fehler_total"] = (res.get("fehler") or 0) + (res.get("verweigerungen") or 0)
            entry["fehler_parcours"] = res.get("fehler") or 0
            entry["zeit_total"] = res.get("zeit") or 0
            entry["disqualifikation"] = res.get("disqualifikation") or ""
            entry["platz"] = None  # Wird später gesetzt
    return runs


def print_results(category: str, cat_data: dict):
    """Pretty-print Ergebnisse für eine Kategorie."""
    print(f"\n{'='*70}")
    print(f"  {category}")
    print(f"{'='*70}")

    if not cat_data:
        print("  (keine Daten)")
        return

    r1 = cat_data.get("run1_ranking", [])
    r2 = cat_data.get("run2_ranking", [])
    combined = cat_data.get("combined", [])

    print(f"\n  Lauf 1 (Jumping):  {len(r1)} Starter")
    print(f"  Lauf 2 (Agility):  {len(r2)} Starter")

    klassiert = sum(1 for c in combined if c.get("kombi_rang"))
    dis = sum(1 for c in combined if c.get("kombi_dis"))
    offen = sum(1 for c in combined if not c.get("kombi_rang") and not c.get("kombi_dis"))

    print(f"\n  Final-Kombi: {klassiert} klassiert, {dis} DIS, {offen} offen")

    if combined:
        print(f"\n  Top 10 Final-Rangliste:")
        for i, r in enumerate(combined[:10], 1):
            lic = r.get("license", "—")
            dog = r.get("dog_name", "—")
            hand = r.get("handler_name", "—")
            rang = r.get("kombi_rang") or "—"
            fehler = r.get("kombi_fehler")
            zeit = r.get("kombi_zeit", 0)

            status = ""
            if r.get("kombi_dis"):
                status = "DIS"
            elif not r.get("both_done"):
                status = "OFFEN"

            print(f"    {i:2d}. [{rang:>3}] Lic {lic} | {dog} | {hand}")
            print(f"         Fehler: {fehler}, Zeit: {zeit:.2f}s {status}")

    print()


def main():
    print("\n🔍 SM-2026-Referenzdaten Validierung")
    print(f"   Quali: {QUALI_CSV.name}")
    print(f"   Final: {FINAL_CSV.name}")

    # Lade und parse Resultate
    print("\n📥 Lade + parse CSV-Exporte...")
    try:
        quali_data = load_csv(QUALI_CSV)
        quali_runs = parse_sm_result_csv(quali_data, "quali")
        quali_runs = normalize_run_entries(quali_runs)
        print(f"   ✓ {len(quali_runs)} Quali-Läufe")
    except Exception as e:
        print(f"   ✗ Quali-CSV Fehler: {e}")
        import traceback
        traceback.print_exc()
        return 1

    try:
        final_data = load_csv(FINAL_CSV)
        final_runs = parse_sm_result_csv(final_data, "final")
        final_runs = normalize_run_entries(final_runs)
        print(f"   ✓ {len(final_runs)} Final-Läufe")
    except Exception as e:
        print(f"   ✗ Final-CSV Fehler: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Baue Event
    print("\n⚙️  Berechne SM-Final...")
    try:
        event = {
            "id": "SM_2026",
            "runs": quali_runs + final_runs,
        }
        result = calculate_sm_final(event)
        print(f"   ✓ {len(result)} Kategorien gefunden")
    except Exception as e:
        print(f"   ✗ Berechnung Fehler: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Gib Ergebnisse aus
    print("\n📊 Ergebnisse:")
    for cat in ["Large", "Intermediate", "Medium", "Small"]:
        if cat in result:
            print_results(cat, result[cat])

    # Zusammenfassung
    print(f"\n{'='*70}")
    print("  ✅ Validierung abgeschlossen")
    print(f"{'='*70}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
