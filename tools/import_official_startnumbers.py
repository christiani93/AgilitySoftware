import argparse
import json
import os
from typing import Any, Dict, List


def load_json(path: str, default: Any):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def as_int(v):
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def main(startlist_json_path: str, sort_entries: bool):
    # 1) Startnummern aus (PDF->JSON) lesen: Lizenz -> Startnummer (+ Rohzeile)
    combined: List[Dict[str, Any]] = load_json(startlist_json_path, [])
    if not isinstance(combined, list):
        raise SystemExit(f"startlist JSON ist nicht eine Liste: {startlist_json_path}")

    by_license: Dict[str, Dict[str, Any]] = {}
    for row in combined:
        if not isinstance(row, dict):
            continue
        lic = (row.get("license") or "").strip()
        if not lic:
            continue
        sn = as_int(row.get("start_no"))
        if sn is None:
            continue

        # Wenn Lizenz mehrfach vorkommt: erste behalten, aber Konflikt sichtbar machen
        if lic in by_license and by_license[lic].get("Startnummer_offiziell") != sn:
            by_license[lic]["Konflikt_Startnummern"] = sorted(
                list({by_license[lic].get("Startnummer_offiziell"), sn})
            )
            continue

        by_license[lic] = {
            "Startnummer_offiziell": sn,
            "Quelle": row.get("quelle"),
            "raw_line": row.get("raw_line"),
        }

    # 2) Stammdaten laden
    dogs_path = os.path.join("data", "dogs.json")
    events_path = os.path.join("data", "events.json")

    dogs = load_json(dogs_path, [])
    events = load_json(events_path, [])

    if not isinstance(dogs, list):
        raise SystemExit("data/dogs.json ist nicht eine Liste.")
    if not isinstance(events, list):
        raise SystemExit("data/events.json ist nicht eine Liste.")

    # 3) Dogs updaten (nur Debug-Felder)
    updated_dogs = 0
    for d in dogs:
        if not isinstance(d, dict):
            continue
        lic = (d.get("Lizenznummer") or "").strip()
        if not lic:
            continue
        info = by_license.get(lic)
        if not info:
            continue

        d["Startnummer_offiziell"] = info["Startnummer_offiziell"]
        d["Startnummer_offiziell_quelle"] = info.get("Quelle")
        updated_dogs += 1

    # 4) Optional: auch in Event-Entries ablegen + sortieren
    updated_entries = 0
    for ev in events:
        if not isinstance(ev, dict):
            continue

        # unterschiedliche Strukturen tolerant behandeln
        runs = ev.get("runs") or ev.get("Runs") or []
        if not isinstance(runs, list):
            continue

        for run in runs:
            if not isinstance(run, dict):
                continue
            entries = run.get("entries") or run.get("Entries") or []
            if not isinstance(entries, list):
                continue

            for e in entries:
                if not isinstance(e, dict):
                    continue
                lic = (e.get("Lizenznummer") or "").strip()
                if not lic:
                    continue
                info = by_license.get(lic)
                if not info:
                    continue

                e["Startnummer_offiziell"] = info["Startnummer_offiziell"]
                updated_entries += 1

            if sort_entries and entries:
                def key(x):
                    v = as_int(x.get("Startnummer_offiziell"))
                    return (0, v) if v is not None else (1, 999999)

                entries_sorted = sorted(entries, key=key)
                # zurückschreiben in dasselbe Feld, das vorhanden war
                if "entries" in run:
                    run["entries"] = entries_sorted
                else:
                    run["Entries"] = entries_sorted

    # 5) Speichern
    save_json(dogs_path, dogs)
    save_json(events_path, events)

    # 6) Debug-Map zusätzlich speichern (für 1:1 Vergleich)
    save_json(os.path.join("data", "debug_startnumbers_offiziell.json"), by_license)

    print(f"[OK] Startnummern gefunden: {len(by_license)}")
    print(f"[OK] Dogs aktualisiert: {updated_dogs}")
    print(f"[OK] Event-Entries aktualisiert: {updated_entries}")
    print("[OK] Zusätzlich gespeichert: data/debug_startnumbers_offiziell.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Debug-Import offizieller Startnummern aus PDF-Startlisten-JSON")
    ap.add_argument("--startlist", required=True, help="Pfad zu startlist_all_combined.json")
    ap.add_argument("--sort-entries", action="store_true", help="Entries pro Run nach offizieller Startnummer sortieren")
    args = ap.parse_args()
    main(args.startlist, args.sort_entries)
