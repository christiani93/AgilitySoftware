"""
Kombinationsranglisten (Generisch)
==================================
Kombiniert zwei Lauf-Resultate zu einer Rangliste nach Agility-Reglement §5.

Nutzbar für:
- SM: Quali (Agility + Jumping) oder Final (Jumping + Agility)
- Andere Events: 2-Lauf-Kombinationen
- KO-Systeme: Vorlauf + Finale

Tiebreaker (§5):
1. Gesamtfehler (kleiner = besser)
2. Gesamtzeit (kürzer = besser)
3. Parcoursfehler (weniger = besser)
4. Besseres Resultat Lauf 1
5. Besseres Resultat Lauf 2
6. Los (nicht implementiert — müsste extern behandelt werden)
"""


def _norm_entry(run1_result, run2_result):
    """Normalisiert einen Eintrag aus zwei Läufen (oder None wenn nicht vorhanden)."""
    if run1_result is None or run2_result is None:
        return None

    r1 = run1_result
    r2 = run2_result

    # Beide müssen klassiert sein (nicht DIS)
    r1_dis = r1.get("dis", False)
    r2_dis = r2.get("dis", False)
    kombi_dis = r1_dis or r2_dis

    # Prüfe ob beide gelaufen sind (für Kombi-Gültigkeit)
    r1_done = r1.get("done", False)
    r2_done = r2.get("done", False)
    both_done = r1_done and r2_done

    return {
        "license": r1.get("license", ""),
        "dog_name": r1.get("dog_name", "") or r2.get("dog_name", ""),
        "handler_name": r1.get("handler_name", "") or r2.get("handler_name", ""),

        # Lauf 1
        "run1_fehler": r1.get("fehler_total", 999),
        "run1_parcours": r1.get("fehler_parcours", 0),
        "run1_zeit": r1.get("zeit", 999.99),
        "run1_dis": r1_dis,
        "run1_rang": r1.get("rang"),

        # Lauf 2
        "run2_fehler": r2.get("fehler_total", 999),
        "run2_parcours": r2.get("fehler_parcours", 0),
        "run2_zeit": r2.get("zeit", 999.99),
        "run2_dis": r2_dis,
        "run2_rang": r2.get("rang"),

        # Kombi
        "kombi_dis": kombi_dis,
        "both_done": both_done,
        "kombi_fehler": 999 if kombi_dis else (r1.get("fehler_total", 0) + r2.get("fehler_total", 0)),
        "kombi_parcours": (r1.get("fehler_parcours", 0) or 0) + (r2.get("fehler_parcours", 0) or 0),
        "kombi_zeit": 999.99 if kombi_dis else (r1.get("zeit", 0) + r2.get("zeit", 0)),
    }


def _sort_key(entry):
    """Sortierkriterium für Kombinationsrangliste (§5 Agility-Reglement).

    1. Klassiert vs. nicht klassiert
    2. Gesamtfehler
    3. Gesamtzeit
    4. Parcoursfehler
    5. Lauf-1-Zeit (besseres Resultat)
    6. Lauf-2-Zeit
    """
    return (
        0 if (entry.get("both_done") and not entry["kombi_dis"]) else 1,
        entry["kombi_fehler"],            # 1. Gesamtfehlerpunkte
        entry.get("kombi_parcours", 0),  # 2. Parcoursfehler-Summe (VOR Zeit!)
        entry["kombi_zeit"],              # 3. Laufzeit-Summe
        entry.get("run1_zeit", 999.99),  # 4. Besseres Agility-Resultat
        entry.get("run2_zeit", 999.99),  # 5. Besseres Jumping-Resultat
    )


def calculate_combination(run1_results: list, run2_results: list) -> list:
    """Berechnet Kombinationsrangliste aus zwei Lauf-Resultatlisten.

    Args:
        run1_results: Liste von Ergebnissen aus Lauf 1 (normalisiert)
        run2_results: Liste von Ergebnissen aus Lauf 2 (normalisiert)

    Returns:
        Liste von Kombinationsergebnissen, sortiert nach §5, mit kombi_rang gesetzt.
    """
    by_lic_1 = {r.get("license", ""): r for r in run1_results if r.get("license")}
    by_lic_2 = {r.get("license", ""): r for r in run2_results if r.get("license")}

    # Alle Lizenzen sammeln
    licenses = set(by_lic_1.keys()) | set(by_lic_2.keys())

    # Kombinieren
    combined = []
    for lic in licenses:
        entry = _norm_entry(by_lic_1.get(lic), by_lic_2.get(lic))
        if entry:
            combined.append(entry)

    # Sortieren
    combined.sort(key=_sort_key)

    # Rang vergeben (nur klassierte)
    rank = 1
    for entry in combined:
        if entry.get("both_done") and not entry.get("kombi_dis"):
            entry["kombi_rang"] = rank
            rank += 1
        else:
            entry["kombi_rang"] = None

    return combined


def get_podium(combined_results: list, places: int = 3) -> list:
    """Extrahiert Siegertreppe (Top N klassiert)."""
    ranked = [r for r in combined_results if r.get("kombi_rang")]
    return ranked[:places]


def get_leader(combined_results: list):
    """Extrahiert aktuellen Führenden (Rang 1, oder None)."""
    return next((r for r in combined_results if r.get("kombi_rang") == 1), None)
