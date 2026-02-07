# Debug Tools

## Offizielle Startnummern importieren (PDF-Startliste)

**Zweck:** offizielles PDF-Startlisten-Mapping als Debug-Felder importieren.

**Beispielaufruf (Windows):**

```bash
python tools/import_official_startnumbers.py --startlist "C:\...\startlist_all_combined.json" --sort-entries
```

**Output:**

- `data/debug_startnumbers_offiziell.json`
- Debug-Felder in `data/dogs.json` und `data/events.json`

### Akzeptanzkriterien / Tests (manuell)

- Script läuft ohne Crash, wenn `data/` existiert und `dogs.json` + `events.json` gültig sind.
- Nach Run existiert `data/debug_startnumbers_offiziell.json`.
- Mindestens ein Hund hat danach `Startnummer_offiziell` gesetzt (wenn Lizenz matcht).
- `--sort-entries` sortiert nur nach Debug-Feld, verändert keine anderen Felder.
