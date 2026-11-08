"""
SM Einzel – Final-Auswertung
============================
Reglement Agility Einzel SM, gültig ab 01.01.2025, §3.5 „Final".

Der Final besteht je Kategorie aus zwei Läufen:
  - Lauf 1 = Jumping  (``final_jumping``) – Startreihenfolge per Zufalls-Los.
  - Lauf 2 = Agility   (``final_agility``) – Startreihenfolge in UMGEKEHRTER Reihenfolge
    zur Rangliste des 1. Laufs (§3.5: „Im zweiten Lauf wird in umgekehrter Reihenfolge
    zur Rangliste des ersten Laufs gestartet.").

Titelrelevant ist die **Kombinationsrangliste der beiden Finalläufe** (§3.5):
  1. kleinere Summe der Gesamtfehlerpunkte
  2. kleinere Summe der Parcoursfehler
  3. kleinere Summe der Laufzeiten
  4. besseres Resultat im Agility-Lauf
  5. besseres Resultat im Jumping-Lauf
  6. Los
Das Siegerteam ist Schweizermeister seiner Kategorie.

Dieselbe Tiebreaker-Logik wie die Quali-Kombi (sm_qualification), nur über die
Finalläufe statt die Qualiläufe.
"""
from sm_qualification import CATEGORIES

FINAL_RUN_TYPES = ("final_jumping", "final_agility")
_DIS_STATES = ("DIS", "ABR", "DNS")


def get_final_runs(event: dict) -> dict:
    """{category: {"final_jumping": run, "final_agility": run}} (nur vorhandene)."""
    result: dict = {}
    for run in event.get("runs", []):
        rt = run.get("sm_run_type")
        if rt not in FINAL_RUN_TYPES:
            continue
        result.setdefault(run.get("kategorie", ""), {})[rt] = run
    return result


def _norm_entry(e: dict) -> dict:
    """Normalisiert EINEN Entry eines Finallaufs aus den von recalc_and_store
    zurückgeschriebenen Entry-Feldern. Trennt — anders als der Quali-Normalisierer —
    'noch nicht gelaufen' (fehler_total 998 / fehlt, kein DIS) sauber von echtem DIS
    (fehler_total 999 bzw. disqualifikation gesetzt). Das braucht das Live-Board, um
    Reststarter / aktuellen Läufer korrekt zu bestimmen."""
    lic = (e.get("Lizenznummer") or "").strip()
    dis_val = (e.get("disqualifikation") or "")
    ft = e.get("fehler_total")
    is_dis = dis_val in _DIS_STATES or (ft is not None and ft >= 999)
    is_dns = dis_val == "DNS"
    # 'done' = Lauf steht fest: entweder gelaufen (echte Fehlerzahl < 998) oder DIS/ABR/DNS.
    done = (dis_val in _DIS_STATES) or (ft is not None and ft < 998)
    return {
        "license":      lic,
        "dog_name":     e.get("Hundename") or e.get("dog_name") or "",
        "handler_name": ((e.get("Vorname", "") + " " + e.get("Nachname", "")).strip()
                         or e.get("handler_name") or ""),
        "fehler_total":    999 if is_dis else (ft if ft is not None else 998),
        "fehler_parcours": e.get("fehler_parcours", 0) or 0,
        "zeit":            999.99 if is_dis else (e.get("zeit_total") if e.get("zeit_total") is not None else 998.99),
        "dis":             is_dis,
        "dns":             is_dns,
        "done":            done,
        "rang":            e.get("platz"),
    }


def _norm_run(run: dict) -> list:
    """Normalisierte Ergebnisliste eines Finallaufs (ohne Entries ohne Lizenz)."""
    return [_norm_entry(e) for e in (run.get("entries", []) if run else []) if (e.get("Lizenznummer") or "").strip()]


def _has_result(r: dict) -> bool:
    """Hat dieses normalisierte Ergebnis einen feststehenden Lauf (gelaufen ODER DIS/ABR/DNS)?"""
    return bool(r.get("done"))


def rank_final_run(run: dict) -> list:
    """Einzel-Lauf-Rangliste (klassierte zuerst nach Rang, dann DIS, dann offen).
    Nutzt die durch recalc_and_store zurückgeschriebenen Entry-Felder."""
    results = _norm_run(run)
    def _key(r):
        return (
            0 if (not r["dis"] and r.get("rang")) else 1,   # 1) klassiert zuerst
            r.get("rang") or 9999,                           # 2) nach Rang
            0 if r["done"] else 1,                           # 3) unter Unklassierten: DIS vor offen
            r.get("fehler_total", 999),
            r.get("zeit", 999.99),
        )
    ranked = sorted(results, key=_key)
    for pos, r in enumerate(ranked, 1):
        r["run_pos"] = pos
    return ranked


def _combine(r_ag, r_ju):
    """Kombi-Werte aus Agility- (r_ag) + Jumping-Resultat (r_ju) eines Teams.
    Klassiert nur, wenn BEIDE Läufe klassiert sind (Agility-Reglement §5)."""
    if r_ag is None or r_ju is None:
        return None
    ag_dis = r_ag["dis"]
    ju_dis = r_ju["dis"]
    both_done = _has_result(r_ag) and _has_result(r_ju)
    kombi_dis = ag_dis or ju_dis
    return {
        "license":       r_ag["license"],
        "dog_name":      r_ag.get("dog_name") or r_ju.get("dog_name"),
        "handler_name":  r_ag.get("handler_name") or r_ju.get("handler_name"),
        "ag_fehler":     r_ag["fehler_total"],
        "ag_parcours":   r_ag.get("fehler_parcours", 0),
        "ag_zeit":       r_ag["zeit"],
        "ag_dis":        ag_dis,
        "ag_rang":       r_ag.get("rang"),
        "ju_fehler":     r_ju["fehler_total"],
        "ju_parcours":   r_ju.get("fehler_parcours", 0),
        "ju_zeit":       r_ju["zeit"],
        "ju_dis":        ju_dis,
        "ju_rang":       r_ju.get("rang"),
        "kombi_dis":     kombi_dis,
        "both_done":     both_done,
        "kombi_fehler":  999 if kombi_dis else r_ag["fehler_total"] + r_ju["fehler_total"],
        "kombi_parcours": (r_ag.get("fehler_parcours") or 0) + (r_ju.get("fehler_parcours") or 0),
        "kombi_zeit":    999.99 if kombi_dis else r_ag["zeit"] + r_ju["zeit"],
    }


def _kombi_sort_key(r):
    """§3.5 Tiebreaker: Gesamtfehler → Laufzeit → Parcoursfehler → Agility → Jumping.
    Teams ohne gültige, vollständige Kombination (DIS in einem Lauf ODER ein Lauf noch
    offen) werden ans Ende sortiert und erhalten keinen Kombi-Rang."""
    return (
        0 if (r.get("both_done") and not r["kombi_dis"]) else 1,
        r["kombi_fehler"],
        r["kombi_zeit"],
        r.get("kombi_parcours", 0),
        r.get("ag_zeit", 999.99),   # besseres Agility-Resultat
        r.get("ju_zeit", 999.99),   # besseres Jumping-Resultat
    )


def calculate_sm_final(event: dict) -> dict:
    """Final-Auswertung je Kategorie.

    Pro Kategorie:
      {
        "has_run1": bool, "has_run2": bool,
        "run1_ranking": [...],     # Jumping (Lauf 1), Einzel-Rangliste
        "run2_ranking": [...],     # Agility (Lauf 2), Einzel-Rangliste
        "combined": [...],         # Final-Kombirangliste (kombi_rang gesetzt), titelrelevant
        "champion": {...} | None,  # Schweizermeister (Rang 1 der Kombi, nur wenn klassiert)
        "complete": bool,          # beide Finalläufe für alle vollständig?
      }
    """
    final_runs = get_final_runs(event)
    output = {}
    for cat in CATEGORIES:
        runs = final_runs.get(cat, {})
        run1 = runs.get("final_jumping")   # Lauf 1
        run2 = runs.get("final_agility")   # Lauf 2
        if not run1 and not run2:
            continue

        r1 = rank_final_run(run1) if run1 else []
        r2 = rank_final_run(run2) if run2 else []
        by_lic_1 = {r["license"]: r for r in r1}
        by_lic_2 = {r["license"]: r for r in r2}

        licenses = list(by_lic_1) + [l for l in by_lic_2 if l not in by_lic_1]
        combined = []
        for lic in licenses:
            r = _combine(by_lic_2.get(lic), by_lic_1.get(lic))
            if r:
                combined.append(r)

        combined.sort(key=_kombi_sort_key)
        rank = 1
        for r in combined:
            if not r["kombi_dis"] and r["both_done"]:
                r["kombi_rang"] = rank
                rank += 1
            else:
                r["kombi_rang"] = None

        champion = next((r for r in combined if r.get("kombi_rang") == 1), None)
        complete = bool(r1) and bool(r2) and all(r["both_done"] for r in combined)

        output[cat] = {
            "has_run1":     run1 is not None,
            "has_run2":     run2 is not None,
            "run1_ranking": r1,
            "run2_ranking": r2,
            "combined":     combined,
            "champion":     champion,
            "complete":     complete,
        }
    return output


def derive_final_run2_startorder(event: dict, category: str) -> list:
    """§3.5: Startreihenfolge 2. Finallauf (Agility) = UMGEKEHRTE Reihenfolge zur
    Rangliste des 1. Laufs (Jumping).

    Rückgabe (in Startreihenfolge Lauf 2): Liste von
      {start_pos, license, dog_name, handler_name, run1_rang, run1_fehler,
       run1_zeit, run1_dis}
    Nicht klassierte (DIS/offen) des 1. Laufs stehen in der 1.-Lauf-Rangliste zuletzt
    → nach Umkehrung starten sie im 2. Lauf ZUERST (gängige Praxis; am offiziellen
    Startlisten-Abgleich zu verifizieren)."""
    final_runs = get_final_runs(event)
    run1 = final_runs.get(category, {}).get("final_jumping")
    if not run1:
        return []
    ranking = rank_final_run(run1)          # klassierte zuerst, DIS/offen zuletzt
    reversed_order = list(reversed(ranking))
    out = []
    for pos, r in enumerate(reversed_order, 1):
        out.append({
            "start_pos":    pos,
            "license":      r["license"],
            "dog_name":     r.get("dog_name", ""),
            "handler_name": r.get("handler_name", ""),
            "run1_rang":    r.get("rang"),
            "run1_fehler":  None if r["dis"] else r.get("fehler_total"),
            "run1_zeit":    None if r["dis"] else r.get("zeit"),
            "run1_dis":     r["dis"],
        })
    return out


def _run_sct(run: dict):
    """Standardzeit (gerundet) eines Laufs nach recalc_and_store, für Zeit-Fehler-Umrechnung."""
    ld = (run or {}).get("laufdaten") or {}
    return ld.get("standardzeit_sct_gerundet") or ld.get("standardzeit_sct")


def live_run2_board(event: dict, category: str) -> dict:
    """Live-Board für den 2. Finallauf (Agility).

    Zeigt für den aktuell startenden Läufer die Vorgabe, die er sich noch erlauben darf,
    um **Platz 1 der Kombinationswertung** zu übernehmen, plus sein Resultat aus dem
    1. Lauf (und wie viele noch starten). Progressiv: der „Führende" ist das beste
    Kombi-Team unter denen, die den 2. Lauf schon absolviert haben.

    Rückgabe:
      {
        "category", "sct_run2",
        "start_order": [ {..§3.5 Startreihenfolge.., "status": done|current|pending,
                          "combined": {..}|None, "takeover": {..}|None }, ... ],
        "leader": {..kombi-Eintrag des aktuell Führenden..} | None,
        "current": {..aktueller Läufer..} | None,
        "remaining": int,   # Teams, die den 2. Lauf noch nicht gelaufen sind
      }
    """
    final = calculate_sm_final(event)
    cat = final.get(category, {})
    run2 = get_final_runs(event).get(category, {}).get("final_agility")
    sct2 = _run_sct(run2)

    r1_by_lic = {r["license"]: r for r in cat.get("run1_ranking", [])}
    r2_by_lic = {r["license"]: r for r in cat.get("run2_ranking", [])}
    combined_by_lic = {r["license"]: r for r in cat.get("combined", [])}

    start_order = derive_final_run2_startorder(event, category)

    # Aktueller Führender = bestes Kombi-Team, das beide Läufe absolviert hat.
    done_combined = [r for r in cat.get("combined", []) if r.get("both_done") and not r["kombi_dis"]]
    done_combined.sort(key=_kombi_sort_key)
    leader = done_combined[0] if done_combined else None

    # Aktueller Läufer = erster in Startreihenfolge ohne Resultat im 2. Lauf.
    current_lic = None
    remaining = 0
    for row in start_order:
        r2 = r2_by_lic.get(row["license"])
        if not (r2 and _has_result(r2)):
            remaining += 1
            if current_lic is None:
                current_lic = row["license"]

    board = []
    for row in start_order:
        lic = row["license"]
        r2 = r2_by_lic.get(lic)
        done = bool(r2 and _has_result(r2))
        status = "done" if done else ("current" if lic == current_lic else "pending")
        board.append({
            **row,
            "status":   status,
            "combined": combined_by_lic.get(lic),
            "takeover": _takeover(r1_by_lic.get(lic), leader, sct2) if not done else None,
        })

    current = combined_by_lic.get(current_lic) if current_lic else None
    return {
        "category":    category,
        "sct_run2":    sct2,
        "start_order": board,
        "leader":      leader,
        "current":     current,
        "current_takeover": _takeover(r1_by_lic.get(current_lic), leader, sct2) if current_lic else None,
        "current_run1":     r1_by_lic.get(current_lic) if current_lic else None,
        "remaining":   remaining,
    }


def _takeover(run1_result, leader, sct2):
    """Was darf sich ein Läufer im 2. Lauf (Agility) erlauben, um Platz 1 der Kombi
    zu übernehmen? Gegeben sein 1.-Lauf-Resultat (Jumping) + der aktuell Führende.

    Rückgabe:
      {
        "possible": bool,
        "reason": str,                 # Kurzbegründung / Status
        "max_fault_points": int|None,  # erlaubte Gesamtfehlerpunkte im 2. Lauf (Übernahme bei < diesem Wert;
                                        #   bei == entscheidet Zeit); None wenn kein Führender
        "max_clean_time": float|None,  # max. Laufzeit 2. Lauf bei fehlerfreiem Lauf, um Führung auf
                                        #   Fehlerpunkte zu halten (= sct2 + margin)
        "equal_fault_time": float|None,# bei exakt gleichen Gesamtfehlerpunkten: Laufzeit-Grenze (Kombi-Zeit < Führender)
      }
    Hinweis: Parcoursfehler-Tiebreak (§3.5 Punkt 2) wird für die Zeit-Angabe als 0 angenommen
    (fehlerfreier Lauf). Die Angaben sind Entscheidungshilfe, die Rangierung selbst macht
    calculate_sm_final exakt nach Reglement."""
    if run1_result is None:
        return {"possible": False, "reason": "kein 1.-Lauf-Resultat",
                "max_fault_points": None, "max_clean_time": None, "equal_fault_time": None}
    if run1_result["dis"]:
        # Mit DIS im 1. Lauf keine gültige Kombination → nicht titelfähig.
        return {"possible": False, "reason": "DIS im 1. Lauf – keine Kombiwertung",
                "max_fault_points": None, "max_clean_time": None, "equal_fault_time": None}
    if leader is None:
        return {"possible": True, "reason": "noch kein Führender – gültiger Lauf führt",
                "max_fault_points": None, "max_clean_time": None, "equal_fault_time": None}

    j_fehler = run1_result.get("fehler_total", 999)
    j_zeit   = run1_result.get("zeit", 999.99)
    L_fehler = leader["kombi_fehler"]
    L_zeit   = leader["kombi_zeit"]

    margin = L_fehler - j_fehler         # erlaubte Gesamtfehlerpunkte im 2. Lauf
    equal_fault_time = round(L_zeit - j_zeit, 2) if (L_zeit - j_zeit) > 0 else None

    if margin < 0:
        return {"possible": False,
                "reason": f"1.-Lauf-Fehler ({j_fehler}) > Führender-Kombi ({L_fehler}) – nicht mehr möglich",
                "max_fault_points": None, "max_clean_time": None, "equal_fault_time": None}

    max_clean_time = round(sct2 + margin, 2) if sct2 is not None else None
    return {
        "possible": True,
        "reason": ("fehlerfrei & unter Zeit → Platz 1" if margin == 0
                   else f"bis {margin} Fehlerpunkte im 2. Lauf erlaubt"),
        "max_fault_points": margin,
        "max_clean_time": max_clean_time,
        "equal_fault_time": equal_fault_time,
    }
