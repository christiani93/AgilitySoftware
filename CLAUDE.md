# AgilitySoftware

Lokale Anwendung zur Agility-Auswertung.

## Schwester-Projekt mit geteiltem Memory

**AgilityPortal** (`C:\Users\chris\OneDrive\Code\AgilityPortal\`)
→ Server-/Web-Komponente desselben Systems.

Beide Projekte teilen den Memory-Pool **AgilityAuswertung** (Junction auf
`~\OneDrive\ClaudeSync\projects-memory\AgilityAuswertung\`). Was du in einer
Session lernst, ist in der anderen verfuegbar. Aendere im Schwesterprojekt
nichts blind ohne hier zu pruefen wie die Datenflusswege aussehen.

## KEINE Verbindung zu VAR / VAR-System

Frueher gabs hier eine vermutete FTP-Pipeline-Notiz — die war falsch.
AgilitySoftware hat **keine** Verbindung zu VAR oder VAR-System. Die
Video-Analyse-Pipeline (VAR ← Fremdsoftware, VAR → OBS-Skripte heute,
VAR → VAR-System kuenftig) laeuft komplett unabhaengig.

## Cross-Project-Junction (bewusst behalten)

VAR-System hat eine Junction unter `VAR-System\_related\AgilitySoftware\`
fuer Read+Edit-Zugriff aus VAR-System-Sessions. Aktuell wird sie nicht
aktiv genutzt (beide Projekte sind noch in der Eigenentwicklung), aber sie
bleibt bewusst bestehen — so wissen beide Systeme bereits voneinander, und
spaeter kann die Integration ohne Setup-Aufwand begonnen werden.
