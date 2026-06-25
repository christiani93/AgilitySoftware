# Stream Deck Plugin — Agility Live

Hardware-Plugin für **Stream Deck Plus** und **Stream Deck XL** zur
schnellen Live-Eingabe am Ring-PC während eines Agility-Laufs.

**Browser-basiert (SDK v2)** — analog zum bestehenden VAR-Plugin.
Keine Node.js / npm Installation nötig.

## Drei Live-Aktionen + Settings

| Action | Wirkung am aktuellen Starter des konfigurierten Rings |
|---|---|
| **Verbindung & Ring** | Property Inspector: Host + Port + Ring setzen, Verbindung testen |
| **Startfreigabe** | Triggert Start-Impuls (Starter wechselt zum nächsten) |
| **Fehler** | +1 Parcoursfehler |
| **Verweigerung** | +1 Verweigerung |

Alle drei Live-Aktionen rufen lokale Software-Endpunkte:
- `POST http://<host>:<port>/api/sd/start_release`
- `POST http://<host>:<port>/api/sd/fault`
- `POST http://<host>:<port>/api/sd/refusal`

Body: `{"ring": "1"}` (oder Ring 2/3, je nach Settings).

## Installation

### Option A: One-Click Setup-Skript (empfohlen für den Ziel-PC)

Doppelklick auf **`install.bat`** — das Skript:
1. Beendet Stream Deck App
2. Kopiert Plugin-Ordner in `%APPDATA%\Elgato\StreamDeck\Plugins\`
3. Startet Stream Deck App wieder

Danach in der Stream Deck App: Linke Seite → Kategorie **"Agility"** → Aktionen
auf Buttons ziehen.

### Option B: Distributable `.streamDeckPlugin` Datei

Auf einem PC mit dem Plugin-Quellcode: Doppelklick auf **`pack.bat`** →
erzeugt `tech.z-b.agility-live.streamDeckPlugin`. Diese Datei auf den
Ziel-PC kopieren, Doppelklick → Stream Deck App fragt nach Installation.

### Option C: Symlink (für Entwicklung)

```powershell
# Als Admin in PowerShell:
New-Item -ItemType SymbolicLink `
    -Path "$env:APPDATA\Elgato\StreamDeck\Plugins\tech.z-b.agility-live.sdPlugin" `
    -Target "C:\Users\chris\OneDrive\Code\AgilitySoftware\tools\streamdeck-agility-live\tech.z-b.agility-live.sdPlugin"
```

## Bedienung

1. Stream Deck App öffnen → "Plugins" → "Agility" → Aktionen finden
2. **"Verbindung & Ring"** auf einen Button ziehen → Property Inspector öffnen:
   - Host: `localhost` (Standard), oder IP des Hauptservers für Ring-PCs
   - Port: `5000` (Hauptserver), oder `5001/5002/5003` für Ring-PCs
   - Ring: 1, 2 oder 3
   - Status-Anzeige: grün = OK, rot = nicht erreichbar
3. **"Startfreigabe" / "Fehler" / "Verweigerung"** auf beliebige Buttons ziehen
4. Tastendruck → POST zur Software → grünes Häkchen oder rotes X auf der Taste

Die Settings sind **Global** (für alle Tasten gleichzeitig) — einmal eintragen,
fertig.

## Plugin-Struktur

```
streamdeck-agility-live/
├─ README.md                              ← du bist hier
└─ tech.z-b.agility-live.sdPlugin/
   ├─ manifest.json                       ← Plugin-Metadaten + 4 Actions
   ├─ app.html                            ← Entry-Point (lädt plugin.js)
   ├─ plugin.js                           ← Plugin-Logik (Browser-JS)
   ├─ ui/
   │  └─ server-settings.html             ← Property Inspector
   └─ imgs/
      ├─ plugin.png                       ← Plugin-Icon (Platzhalter, ersetzen)
      └─ actions/
         ├─ start/icon.png + key.png      ← Icons fuer Startfreigabe
         ├─ fault/icon.png + key.png      ← Icons fuer Fehler
         └─ refusal/icon.png + key.png    ← Icons fuer Verweigerung
```

## Server-Endpunkte (Software-Seite)

Bereits in `web_app/blueprints/routes_live.py` implementiert:

| Route | Body | Antwort |
|---|---|---|
| `POST /api/sd/start_release` | `{"ring": "1"}` | `{success, current_starter_lic}` |
| `POST /api/sd/fault` | `{"ring": "1"}` | `{success, lic, fehler, verweigerungen}` |
| `POST /api/sd/refusal` | `{"ring": "1"}` | `{success, lic, fehler, verweigerungen}` |

Alle Endpunkte arbeiten am **aktuellen Starter** des aktiven Laufs am
gewählten Ring (resolved über `event["current_runs_by_ring"]` +
`run["current_starter"]`).

## Bekannte Limitierungen MVP

- Keine Live-State-Anzeige auf den Tasten (Fehler-/Verweigerungs-Stand)
- Stream Deck Plus Touchscreen bleibt leer (kein Polling)
- Keine Undo-Funktion (versehentliches +1 — Korrektur via Web-UI)
- Icons sind 1×1-Platzhalter

Inspired by VAR-Agility-Plugin (gleiches Pattern, gleicher Author).
