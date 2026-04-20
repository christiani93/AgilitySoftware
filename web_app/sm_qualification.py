"""
SM Einzel – Qualifikationsberechnung
=====================================
Reglement gültig ab 01.01.2025

Qualifikationsmodus (pro Kategorie):
- 2 Qualifikationsläufe (Agility + Jumping)
- Top 16% jedes Laufs → direkt für Final qualifiziert
- Restliche Finalplätze → aus Kombinationsrangliste
- Final-Gesamtplätze: max(10, ceil(starters × 0.40)) pro Kategorie
- Titelverteidiger: direkt für Final gesetzt (zählt als eigener Platz)
- Doppelqualifikation: kein Nachrücken, reduziert direkte Plätze

Kombinationsrangliste Tiebreaker (Reglement):
  1) Gesamtfehlerpunkte
  2) Parcoursfehler
  3) Laufzeiten (Summe beider Läufe)
  4) Agility-Lauf allein
  5) Jumping-Lauf allein
  6) Los

Final:
- Lauf 1 (Jumping): Startreihenfolge per Zufalls-Los
- Lauf 2 (Agility): umgekehrte Reihenfolge aus Lauf 1
"""
import math

CATEGORIES = ["Large", "Intermediate", "Medium", "Small"]

SM_RUN_TYPES = {
    "qual_agility":  "Quali Agility",
    "qual_jumping":  "Quali Jumping",
    "final_jumping": "Final Jumping (Lauf 1)",
    "final_agility": "Final Agility (Lauf 2)",
}


def get_sm_runs(event: dict) -> dict:
    """
    Gruppiert SM-Läufe nach Kategorie und sm_run_type.
    Returns: {category: {sm_run_type: run_dict}}
    """
    result: dict = {}
    for run in event.get("runs", []):
        rt = run.get("sm_run_type")
        if not rt or rt not in SM_RUN_TYPES:
            continue
        cat = run.get("kategorie", "")
        if cat not in result:
            result[cat] = {}
        result[cat][rt] = run
    return result


def _get_results_from_run(run: dict) -> list:
    """
    Liest Einträge aus einem Run und gibt eine normalisierte Ergebnisliste zurück.
    Verwendet fehler_total / zeit_total (durch _calculate_run_results befüllt).
    """
    entries = run.get("entries", [])
    results = []
    for e in entries:
        lic = (e.get("Lizenznummer") or "").strip()
        if not lic:
            continue
        dis_val = e.get("disqualifikation") or ""
        is_dis = dis_val in ("DIS", "ABR", "DNS") or e.get("fehler_total", 0) >= 998
        results.append({
            "license":      lic,
            "dog_name":     e.get("Hundename") or e.get("dog_name") or "",
            "handler_name": (
                (e.get("Vorname", "") + " " + e.get("Nachname", "")).strip()
                or e.get("handler_name") or ""
            ),
            "fehler_total":   e.get("fehler_total", 999) if not is_dis else 999,
            "fehler_parcours": e.get("fehler_parcours", 0),
            "zeit":           e.get("zeit_total", 999.99) if not is_dis else 999.99,
            "dis":            is_dis,
            "rang":           e.get("platz"),
        })
    return results


def calculate_sm_qualification(event: dict) -> dict:
    """
    Berechnet SM-Qualifikation für alle Kategorien.

    Rückgabeformat pro Kategorie:
    {
        "starters": int,
        "final_spots": int,
        "direct_per_run": int,
        "has_qa": bool,
        "has_qj": bool,
        "qa_results": [...],
        "qj_results": [...],
        "combined_ranking": [...],   # alle Teilnehmer, sortiert nach Kombi-Rangliste
        "direct_set": [license, ...],
        "final_list": [...],         # direkte Qualifier + Kombi-Nachrücker
        "defending_champion": {...} | None,
    }
    """
    sm_runs = get_sm_runs(event)
    sm_config = event.get("sm_config", {})
    output = {}

    for cat in CATEGORIES:
        cat_runs = sm_runs.get(cat, {})
        qa_run = cat_runs.get("qual_agility")
        qj_run = cat_runs.get("qual_jumping")

        if not qa_run and not qj_run:
            continue

        cat_config = sm_config.get(cat, {})
        defending = cat_config.get("defending_champion")  # {license, dog_name, handler_name} | None

        qa_results = _get_results_from_run(qa_run) if qa_run else []
        qj_results = _get_results_from_run(qj_run) if qj_run else []

        # Starters = nicht-DIS Lizenzen über beide Läufe
        all_licenses = set(
            r["license"] for r in (qa_results + qj_results) if not r["dis"]
        )
        starters = len(all_licenses)

        # Finale Platzzahl und direkte Qualifier-Quota
        final_spots    = max(10, math.ceil(starters * 0.40))
        direct_per_run = math.ceil(starters * 0.16)

        # Direkte Qualifier sammeln
        direct_set: set = set()
        if defending and defending.get("license"):
            direct_set.add(defending["license"])

        def _top_n_licenses(results, n):
            valid = sorted(
                [r for r in results if not r["dis"] and r["rang"] is not None],
                key=lambda r: (r.get("rang") or 9999),
            )
            return [r["license"] for r in valid[:n]]

        for lic in _top_n_licenses(qa_results, direct_per_run):
            direct_set.add(lic)
        for lic in _top_n_licenses(qj_results, direct_per_run):
            direct_set.add(lic)

        # Teilnehmer-Index aufbauen (über beide Läufe)
        idx: dict = {}
        for r in qa_results:
            idx.setdefault(r["license"], {}).update({
                "license":      r["license"],
                "dog_name":     r["dog_name"],
                "handler_name": r["handler_name"],
                "qa_fehler":    r["fehler_total"],
                "qa_parcours":  r["fehler_parcours"],
                "qa_zeit":      r["zeit"],
                "qa_dis":       r["dis"],
                "qa_rang":      r["rang"],
            })
        for r in qj_results:
            idx.setdefault(r["license"], {}).update({
                "license":      r["license"],
                "dog_name":     r["dog_name"],
                "handler_name": r["handler_name"],
                "qj_fehler":    r["fehler_total"],
                "qj_parcours":  r["fehler_parcours"],
                "qj_zeit":      r["zeit"],
                "qj_dis":       r["dis"],
                "qj_rang":      r["rang"],
            })

        # Kombinationsrangliste berechnen
        combined = []
        for lic, data in idx.items():
            qa_f = data.get("qa_fehler", 999)
            qj_f = data.get("qj_fehler", 999)
            qa_z = data.get("qa_zeit", 999.99)
            qj_z = data.get("qj_zeit", 999.99)
            qa_d = data.get("qa_dis", True)
            qj_d = data.get("qj_dis", True)

            if qa_d or qj_d:
                kombi_dis    = True
                kombi_fehler = 999
                kombi_zeit   = 999.99
            else:
                kombi_dis    = False
                kombi_fehler = qa_f + qj_f
                kombi_zeit   = qa_z + qj_z

            combined.append({
                **data,
                "kombi_fehler":    kombi_fehler,
                "kombi_parcours":  data.get("qa_parcours", 0) + data.get("qj_parcours", 0),
                "kombi_zeit":      kombi_zeit,
                "kombi_qa_fehler": qa_f,
                "kombi_qj_fehler": qj_f,
                "kombi_qa_zeit":   qa_z,
                "kombi_qj_zeit":   qj_z,
                "is_direct":       lic in direct_set,
                "is_defending":    bool(defending and lic == defending.get("license")),
                "kombi_dis":       kombi_dis,
            })

        # Sortierung: Tiebreaker gemäß Reglement
        def _kombi_sort(r):
            return (
                1 if r["kombi_dis"] else 0,
                r["kombi_fehler"],
                r.get("kombi_parcours", 0),
                r["kombi_zeit"],
                r.get("kombi_qa_zeit", 999.99),  # Agility-Lauf
                r.get("kombi_qj_zeit", 999.99),  # Jumping-Lauf
            )

        combined.sort(key=_kombi_sort)
        rank = 1
        for r in combined:
            if not r["kombi_dis"]:
                r["kombi_rang"] = rank
                rank += 1
            else:
                r["kombi_rang"] = None

        # Final-Liste zusammenstellen
        direct_list    = [r for r in combined if r["is_direct"] and not r["kombi_dis"]]
        direct_lic_set = {r["license"] for r in direct_list}

        remaining_spots = max(0, final_spots - len(direct_lic_set))
        non_direct      = [r for r in combined
                           if r["license"] not in direct_lic_set and not r["kombi_dis"]]
        combo_list      = non_direct[:remaining_spots]

        final_list = direct_list + combo_list

        output[cat] = {
            "starters":          starters,
            "final_spots":       final_spots,
            "direct_per_run":    direct_per_run,
            "has_qa":            qa_run is not None,
            "has_qj":            qj_run is not None,
            "qa_results":        qa_results,
            "qj_results":        qj_results,
            "combined_ranking":  combined,
            "direct_set":        list(direct_set),
            "final_list":        final_list,
            "defending_champion": defending,
        }

    return output
