# Standalone TIMY-Recorder

Eigenständiges Tool zum Aufzeichnen der TIMY-Rohdaten — **ohne** die
AgilitySoftware (kein Flask, kein Portal, kein `events.json`). Nur `pywin32`
für die echte ALGE-USB-Anbindung; die Kernlogik läuft auch ganz ohne Hardware.

## Wozu

1. **TIMY-Zeitberechnung verifizieren** — jede `C0 → C1`-Rechnung wird gegen
   die vom TIMY selbst gesendete `RT`-Zeile (= Wert auf der **Anzeigetafel**)
   geprüft. `final_time` nutzt *exakt dieselbe* floor-auf-0.01-Formel wie die
   AgilitySoftware; `delta_vs_timy_s` zeigt sofort jede Abweichung (soll `0.00`
   sein — kein manuelles Ablesen der Tafel nötig).
2. **„Zeit zwischen 2 Starts" messen** — Abstand aufeinanderfolgender
   C0-Impulse (Tageszeit). Datengrundlage für die Zeitplan-Optimierung im
   AgilityPortal (Ø Sek/Starter pro Klasse).

## Erkannte Zeilenformate

| Zeile | Bedeutung |
|---|---|
| `0006 C0  13:20:16.0431 00` | Start (Lichtschranke); Kanal `C0`, 4 Nachkommastellen |
| `0006 C1  13:20:21.0159 00` | Stop (Lichtschranke) |
| `0006 RT  00:00:04.97   00` | Laufzeit laut TIMY (= Anzeigetafel) |
| `0001 C0M 13:16:51.38   00` | wie oben, aber **`M` = manuell** (Geräte-Button), 2 Nachkommastellen |
| `?0001 C1M 13:17:01.71  00` | vom TIMY nachträglich korrigierter/markierter Impuls (`?`) |
| `TIMY: 480170000` | laufende Uhr (Rauschen, wird ignoriert/nur gezählt) |
| `n0007` / `s0008` | Status-Marker (nur geloggt) |

Am **Event** (Lichtschranke) kommt das präzise `C0/C1/RT`-Format; die `…M`-Zeilen
entstehen nur bei manueller Button-Auslösung.

### Pairing über die Lauf-Nummer

Start/Stop/RT tragen eine führende **Lauf-Nummer** (`0006`). Das TIMY kann
mehrere Zeiten gleichzeitig laufen lassen (mehrere Hunde gestartet, bevor der
erste im Ziel ist) und paart C0/C1 über diese Nummer. Der Recorder paart ebenso
pro Nummer — ein einzelner Slot würde bei überlappenden Starts falsch zuordnen
(in echten Tests bestätigt: ohne Pairing wurde ein Stop an den falschen Start
gehängt).

## Starten (mit TIMY)

```
start_recorder.bat            REM Ring-Label "Ring 1"
start_recorder.bat "Ring 2"   REM anderes Label
```

Das `.bat` aktiviert das 32-bit `ring_env` (pywin32 + ALGE-USB-Treiber nötig)
und verbindet sich mit dem TIMY. **Strg+C** beendet die Aufzeichnung.

## Testen (ohne TIMY)

```
python timy_recorder.py --simulate 5        REM 5 synthetische Läufe (inkl. RT)
python timy_recorder.py --replay <datei>    REM rohe TIMY-Zeilen ODER eine .log einspielen
```

`--replay` akzeptiert sowohl eine Datei mit je einer rohen TIMY-Zeile pro Zeile
als auch eine vom Recorder erzeugte `.log` (das `raw='…'` wird extrahiert) —
praktisch, um eine echte Aufnahme nachzurechnen.

## Ausgabedateien (neben `timy_recorder.py`)

| Datei | Inhalt |
|---|---|
| `timy_record_<ring>_<zeitstempel>.log` | Mensch-lesbar: Ereignisse + Rechnung + RT-Vergleich |
| `timy_record_<ring>_<zeitstempel>.csv` | Strukturiert, ein Lauf pro Zeile |

CSV-Spalten:

```
idx, run_no, start_tod, stop_tod, raw_diff_s, final_time_s,
timy_rt_s, delta_vs_timy_s, start_interval_s, flags
```

- `run_no` = Lauf-Nummer des TIMY (Pairing-Schlüssel)
- `raw_diff_s` = `stop_s - start_s` **ungerundet**
- `final_time_s` = nach floor auf 0.01 (wie AgilitySoftware)
- `timy_rt_s` = Laufzeit laut TIMY (Anzeigetafel)
- `delta_vs_timy_s` = `final_time_s − timy_rt_s` (soll `0.00` sein)
- `start_interval_s` = Sekunden seit dem vorherigen Start
- `flags` = z.B. `no_c1`, `no_start`, `rt_only`, `corrected`, `no_rt`, `invalid`

Läufe mit C0 aber ohne C1 (Abbruch/DIS/Fehlstart) erscheinen mit leerer
`stop_tod`/`final_time_s`, aber vorhandenem `start_interval_s`.
