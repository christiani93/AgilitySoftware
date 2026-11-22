"""
FMBB-WM Agility Quali — Tag-Auswertung
========================================

Reglement / Modus: siehe Memory project_fmbb_quali.md.
Implementations-Plan: project_fmbb_implementation.md.

Anwendungsfall (User-Klarstellung 2026-06-14):
Die FMBB-Quali wird als **2 separate 1-Tages-Auswertungen** durchgeführt.
Die Saison-Wertung (8+2 qualifizieren mit Streichresultaten) macht der
SKBS-Verband — NICHT diese Software.

Reglement-Stand 2026-11-22 (reference_fmbb_agility_quali_reglement):
- **FMBB-Marker:** explizit pro Anmeldung über `entry["is_fmbb"]`. Bulk-Setzen über
  `mark_fmbb_by_licenses()` mit einer Lizenzliste (vom SKBS). Kein Rasse-Filter.
- **Standardzeit (SCT):** eigene FMBB-SCT = schnellster **Belgischer Schäferhund**
  (FMBB-markiert, wenigste Fehler → beste Zeit) × **1.15**, aufgerundet — unabhängig
  von der normalen Lauf-SCT (die auf dem schnellsten Hund GESAMT basiert). Beleg:
  FMBB WC Agility Implementation Rules 2h („best dog … +15%"); SKBS-Quali-Modus Agility
  („bezieht sich auf den schnellsten Belgischen Schäferhund"). MCT = FCI-Standard.
- **L2+L3 gemeinsam:** L2 läuft bei L3 als „weisser Hund" (`ausser_konkurrenz`), zählt
  NUR für die FMBB-Quali. Die FMBB-Wertung fasst L2+L3 je Disziplin zu EINER Rangliste
  zusammen (gemeinsame SCT-Basis über alle FMBB-BSH der Disziplin).
- **Punkte:** werden JETZT im Tool berechnet (Chris 2026-11-22, „einfacher für die
  SKBS-TK"): Rang→Punkte-Tabelle; ab 15 Parcours-Fehlerpunkten halbe Punkte; bei
  Zeitfehler keine Punkte. Saison-Streichresultate/Selektion macht weiter der SKBS.

Aktivierung:
`event["fmbb_quali_active"] = True` markiert ein Event als FMBB-Quali-Tag
(Overlay über bestehende Veranstaltungsart, kein eigener Typ). Doppelnutzung
mit SKBS-SM möglich am selben Event.
"""
from __future__ import annotations

import math

from utils import _to_float, _to_int


# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

# Klassen die FMBB-startberechtigt sind (project_fmbb_quali.md, Reglement)
FMBB_ELIGIBLE_CLASSES = ("2", "3")

# Relevante Lauftypen
FMBB_RUN_TYPES = ("Agility", "Jumping")

# Ausgabe-Reihenfolge der Disziplinen (FMBB-WM-Laufreihenfolge: Jumping vor Agility).
FMBB_DISCIPLINE_ORDER = ("Jumping", "Agility")

# Zeitfaktor FMBB-WM Agility: Standardzeit = schnellster BSH + 15 %.
FMBB_SCT_FACTOR = 1.15

# Punktevergabe pro Lauf nach Rang (SKBS-Quali-Modus Agility).
FMBB_POINTS_BY_RANK = {
    1: 20, 2: 17, 3: 14, 4: 9, 5: 8, 6: 7,
    7: 6, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1,
}

# Ab dieser Zahl an Parcours-Fehlerpunkten (Abwürfe/Verweigerungen × 5) nur halbe
# Punkte. 15 FP = 3 Parcoursfehler. (Teams mit Zeitfehler bekommen ohnehin 0 Punkte.)
FMBB_HALF_POINTS_FAULT_THRESHOLD = 15

DIS_STATES = ("DIS", "ABR", "DNS")


# ---------------------------------------------------------------------------
# Public API — Aktivierung & Marker
# ---------------------------------------------------------------------------

def is_fmbb_active(event: dict) -> bool:
    """True wenn der Event als FMBB-Quali-Tag markiert ist."""
    return bool(event.get("fmbb_quali_active"))


def is_fmbb_entry(entry: dict) -> bool:
    """
    True wenn die Anmeldung als FMBB-Teilnehmer markiert ist.
    Reine Flag-Prüfung — kein heuristischer Rasse-Filter (User-Entscheid 2026-06-14).
    """
    return bool(entry.get("is_fmbb"))


def mark_fmbb_by_licenses(event: dict, licenses: list[str] | set[str],
                          reset: bool = True) -> dict:
    """
    Bulk-Setzen des `is_fmbb`-Flags über eine Liste von Lizenznummern.

    Wenn `reset=True` (Default): alle Anmeldungen werden zuerst auf
    `is_fmbb=False` gesetzt, dann die in `licenses` enthaltenen auf True.
    Wenn `reset=False`: nur die in `licenses` enthaltenen werden auf True
    gesetzt, andere bleiben unverändert.

    Lizenzen werden case-insensitive verglichen, mit Whitespace-Trim.

    Returns: dict mit Statistik
      {
        "matched":   int,  # Anzahl Anmeldungen mit is_fmbb=True nach Lauf
        "unmatched": list, # Lizenzen aus der Eingabeliste die im Event nicht vorkommen
        "total_entries": int,
      }
    """
    license_set = {str(lic).strip().upper() for lic in licenses if str(lic).strip()}
    found_licenses: set[str] = set()
    matched = 0
    total = 0

    for run in event.get("runs", []):
        for entry in run.get("entries", []):
            total += 1
            entry_lic = (entry.get("Lizenznummer") or "").strip().upper()
            if entry_lic and entry_lic in license_set:
                entry["is_fmbb"] = True
                matched += 1
                found_licenses.add(entry_lic)
            elif reset:
                entry["is_fmbb"] = False

    unmatched = sorted(license_set - found_licenses)
    return {
        "matched":       matched,
        "unmatched":     unmatched,
        "total_entries": total,
    }


# ---------------------------------------------------------------------------
# Public API — Tag-Auswertung
# ---------------------------------------------------------------------------

def calculate_fmbb_quali(event: dict) -> dict:
    """
    Tag-Auswertung für ein FMBB-Quali-Event (Agility).

    L2 und L3 laufen denselben Parcours (L2 als weisse Hunde bei L3). Darum wird
    je **Disziplin** (Agility / Jumping) EINE gemeinsame Rangliste über alle
    FMBB-markierten BSH beider Klassen gebildet:
      1. Standardzeit (SCT) = schnellster FMBB-BSH (wenigste Fehler → beste Zeit,
         innerhalb MCT) × 1.15, aufgerundet. MCT = FCI-Standard (parcours/2.5 Agi,
         parcours/3 Jump).
      2. Pro Team: Parcoursfehler (Abwürfe+Verweigerungen ×5) + Zeitfehler
         (Laufzeit − SCT, ≥0) = Gesamtfehler. Über MCT oder DIS/ABR/DNS → DIS.
      3. Rang nach (Gesamtfehler, Parcoursfehler, Zeit), ex aequo gleicher Rang.
      4. Punkte nach Rang-Tabelle; ab 15 Parcours-FP halbe Punkte; bei Zeitfehler 0.

    Returns:
      {
        "active": bool,
        "runs":   [ {kategorie, klasse, laufart, sct, mct, rankings:[...]}, ... ],
        "total_fmbb_teams": int,   # unique Lizenzen der markierten Teilnehmer
      }
    Jede Ranking-Zeile: license, dog_name, handler_name, klasse, fehler_total,
    fehler_parcours, zeitfehler, zeit, rang, points, dis.
    """
    # FMBB-markierte Entries je Disziplin sammeln (über alle L2/L3-Läufe). Nur Läufe
    # MIT FMBB-Teilnehmern tragen bei (leere Disziplinen entstehen gar nicht erst).
    by_laufart: dict[str, dict] = {}
    for run in event.get("runs", []):
        klasse  = str(run.get("klasse") or "")
        laufart = run.get("laufart") or ""
        if klasse not in FMBB_ELIGIBLE_CLASSES or laufart not in FMBB_RUN_TYPES:
            continue
        fmbb_entries = [
            e for e in (run.get("entries") or [])
            if is_fmbb_entry(e) and (e.get("Lizenznummer") or "").strip()
        ]
        if not fmbb_entries:
            continue
        bucket = by_laufart.setdefault(laufart, {
            "kategorie": run.get("kategorie") or "",
            "classes": set(),
            "parcours_laengen": [],
            "items": [],   # (entry, klasse)
        })
        bucket["classes"].add(klasse)
        laenge = _to_float((run.get("laufdaten") or {}).get("parcours_laenge"), None)
        if laenge:
            bucket["parcours_laengen"].append(laenge)
        for e in fmbb_entries:
            bucket["items"].append((e, klasse))

    result_runs: list[dict] = []
    fmbb_licenses: set[str] = set()

    # Stabile Reihenfolge: Jumping vor Agility (wie FMBB-WM-Laufreihenfolge).
    def _order(la: str) -> int:
        return FMBB_DISCIPLINE_ORDER.index(la) if la in FMBB_DISCIPLINE_ORDER else 99
    for laufart in sorted(by_laufart, key=_order):
        bucket = by_laufart[laufart]
        mct_rounded = _fmbb_mct(laufart, bucket["parcours_laengen"])
        rankings = _rank_fmbb_discipline(bucket["items"], mct_rounded)

        for r in rankings:
            if r["license"]:
                fmbb_licenses.add(r["license"])

        classes = sorted(bucket["classes"])
        result_runs.append({
            "kategorie": bucket["kategorie"],
            "klasse":    "+".join(classes),   # z.B. "2+3"
            "laufart":   laufart,
            "sct":       _sct_for_rankings(rankings),
            "mct":       mct_rounded,
            "rankings":  rankings,
        })

    return {
        "active":            is_fmbb_active(event),
        "runs":              result_runs,
        "total_fmbb_teams":  len(fmbb_licenses),
    }


# ---------------------------------------------------------------------------
# Helpers (intern)
# ---------------------------------------------------------------------------

DIS_SENTINEL_FEHLER = 999.0


def _extract_result(entry: dict) -> dict:
    """Roh-Resultat aus dem Entry (result-Dict oder Legacy-Direktfelder)."""
    return entry.get("result") or {
        "zeit":             entry.get("zeit"),
        "fehler":           entry.get("fehler"),
        "verweigerungen":   entry.get("verweigerungen"),
        "disqualifikation": entry.get("dis_abr") or entry.get("disqualifikation"),
    }


def _fmbb_mct(laufart: str, parcours_laengen: list) -> int | None:
    """FCI-Maximalzeit (gerundet) aus der (identischen) Parcourslänge der Disziplin."""
    laenge = max(parcours_laengen) if parcours_laengen else None
    if not laenge or laenge <= 0:
        return None
    mct = laenge / 3.0 if laufart == "Jumping" else laenge / 2.5
    return math.ceil(mct)


def _fmbb_base_time(items: list, mct_rounded: int | None) -> float | None:
    """Zeit des schnellsten BSH: wenigste Fehler → beste Zeit, nicht-DIS, in MCT."""
    best = None
    for entry, _klasse in items:
        r = _extract_result(entry)
        if r.get("disqualifikation") in DIS_STATES:
            continue
        zeit = _to_float(r.get("zeit"), None)
        if zeit is None:
            continue
        if mct_rounded is not None and zeit > mct_rounded:
            continue
        fehler = _to_int(r.get("fehler", 0) or 0, 0)
        verw   = _to_int(r.get("verweigerungen", 0) or 0, 0)
        cand = (fehler + verw, zeit)
        if best is None or cand < best:
            best = cand
    return best[1] if best else None


def _fmbb_points(rang: int, zeitfehler: float, fehler_parcours: int) -> float:
    """Punkte nach Rang; bei Zeitfehler 0; ab 15 Parcours-FP halbe Punkte."""
    base = FMBB_POINTS_BY_RANK.get(rang, 0)
    if base == 0:
        return 0.0
    if zeitfehler > 0:
        return 0.0
    if fehler_parcours >= FMBB_HALF_POINTS_FAULT_THRESHOLD:
        return base / 2.0
    return float(base)


def _rank_fmbb_discipline(items: list, mct_rounded: int | None) -> list:
    """Baut die gemeinsame FMBB-Rangliste einer Disziplin inkl. SCT/Punkte."""
    base_time = _fmbb_base_time(items, mct_rounded)
    sct_rounded = math.ceil(base_time * FMBB_SCT_FACTOR) if base_time is not None else None

    rows: list[dict] = []
    for entry, klasse in items:
        r = _extract_result(entry)
        dog = entry.get("Hundename") or entry.get("dog_name") or ""
        handler = (
            (entry.get("Vorname", "") + " " + entry.get("Nachname", "")).strip()
            or entry.get("handler_name") or ""
        )
        row = {
            "license":      (entry.get("Lizenznummer") or "").strip(),
            "dog_name":     dog,
            "handler_name": handler,
            "klasse":       klasse,
            "_sct":         sct_rounded,
        }
        dis_val = r.get("disqualifikation")
        zeit = _to_float(r.get("zeit"), None)
        fehler = _to_int(r.get("fehler", 0) or 0, 0)
        verw   = _to_int(r.get("verweigerungen", 0) or 0, 0)
        auto_dis = (mct_rounded is not None and zeit is not None and zeit > mct_rounded)

        if dis_val in DIS_STATES or zeit is None or auto_dis:
            row.update({
                "dis": True, "rang": None, "points": 0.0,
                "fehler_total": DIS_SENTINEL_FEHLER,
                "fehler_parcours": (fehler + verw) * 5,
                "zeitfehler": None,
                "zeit": zeit if zeit is not None else 999.99,
            })
        else:
            fehler_parcours = (fehler + verw) * 5
            zeitfehler = max(0.0, zeit - sct_rounded) if sct_rounded is not None else 0.0
            row.update({
                "dis": False,
                "fehler_parcours": fehler_parcours,
                "zeitfehler": zeitfehler,
                "fehler_total": fehler_parcours + zeitfehler,
                "zeit": zeit,
            })
        rows.append(row)

    # Rang vergeben: Gesamtfehler → Parcoursfehler → Zeit, ex aequo gleicher Rang.
    ranked = [r for r in rows if not r["dis"]]
    ranked.sort(key=lambda x: (x["fehler_total"], x["fehler_parcours"], x["zeit"]))
    position = 0
    rang = 0
    prev_key = None
    for r in ranked:
        position += 1
        key = (r["fehler_total"], r["fehler_parcours"], r["zeit"])
        if key != prev_key:
            rang = position
            prev_key = key
        r["rang"] = rang
        r["points"] = _fmbb_points(rang, r["zeitfehler"], r["fehler_parcours"])

    dis_rows = [r for r in rows if r["dis"]]
    return ranked + dis_rows


def _sct_for_rankings(rankings: list) -> int | None:
    """Die (einheitliche) FMBB-SCT der Disziplin aus den Zeilen abgreifen."""
    for r in rankings:
        if r.get("_sct") is not None:
            return r["_sct"]
    return None
