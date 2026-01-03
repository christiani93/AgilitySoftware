# Akzeptanz-Testplan (Browser)

Die folgenden Schritte prüfen die wichtigsten SCT/MCT/Zeitfehler/DIS-Regeln manuell im Browser.

## Vorbereitung
1. Anwendung normal starten (wie üblich über deine Start-Skripte).
2. Stelle sicher, dass die Test-Events/ Läufe vorhanden sind oder lege sie an (siehe Testfälle unten).

## Testfälle

### Klasse 1 – Direkt vorgegebene SCT (K1-A)
1. Lauf anlegen: Klasse 1, Agility, SCT direkt = 40 Sekunden.
2. **run_entry** öffnen: SCT=40 und MCT=60 müssen angezeigt werden.
3. Ergebnisse eingeben:
   - 39.99 → Zeitfehler 0.00, kein DIS.
   - 40.01 → Zeitfehler 0.01, kein DIS.
   - 60.00 → kein DIS.
   - 60.01 → DIS ausgelöst.
4. **Ranking** prüfen: SCT/MCT gerundet sichtbar; DIS nur beim letzten Team.
5. **Print /print/ranking_single/** prüfen: Fehler & Verweigerungen werden angezeigt.

### Klasse 1 – SCT aus Geschwindigkeit (K1-B)
1. Lauf anlegen: Klasse 1, Jumping, Parcourslänge 150 m, Geschwindigkeit 3.6 m/s.
2. Erwartung: SCT=42, MCT=63.
3. **run_entry**: SCT=42 und MCT=63 sichtbar.
4. Ergebnis eingeben: 42.01 → Zeitfehler 0.01.
5. Ranking/Print prüfen: Werte sichtbar, keine ungewollte Rundung der Laufzeit.

### Klasse 2 – SCT aus bestplatziertem Team (K2-A)
1. Lauf anlegen: Klasse 2, Agility, Länge 150 m.
2. Teams erfassen:
   - A: Fehler+Verweigerungen=0, Zeit=34.50
   - B: 0, Zeit=35.20
   - C: 5, Zeit=32.00
3. Erwartung: bestplatziert=A → SCT=49, MCT=60.
4. **run_entry**/Ranking prüfen: SCT/MCT gerundet angezeigt, keine Zeitfehler, kein DIS.

### Klasse 2 – DIS-Team bestimmt SCT nicht (K2-B)
1. Gleicher Lauf wie K2-A, zusätzlich Team D: 0 Fehler, Zeit 30.00, DIS.
2. Erwartung: SCT bleibt 49 (Team D ignorieren).
3. Ranking prüfen: SCT unverändert, Team D als DIS.

### Klasse 3 – Jumping mit Faktor 1.3 (K3-A)
1. Lauf anlegen: Klasse 3, Jumping, Länge 150 m.
2. Teams erfassen:
   - A: 0 Fehler, Zeit 34.50 (bestplatziert)
   - B: 0 Fehler, Zeit 35.20
   - C: 5 Fehler, Zeit 32.00
   - Optional D: 0 Fehler, Zeit 45.01 (zeigt Zeitfehler 0.01)
3. Erwartung: SCT=45, MCT=50; D hat Zeitfehler 0.01.
4. **run_entry**/Ranking prüfen: SCT/MCT gerundet sichtbar, D nicht DIS.

### MCT-Grenze (kein DIS bei exakt MCT)
1. Lauf (z. B. Klasse 3 Jumping, Länge 150 → MCT=50).
2. Team SAFE: Zeit=50.00 → kein DIS.
3. Team OVER: Zeit=50.01 → DIS ausgelöst.

### Debug "Testresultate erzeugen"
1. Route **/debug/generate_results/<event_id>** aufrufen.
2. Wenn ein Lauf leeres `standardzeit_sct` hat, darf kein Fehler (ValueError) auftreten; die Laufdaten werden mit Standardwerten berechnet.

## Abschluss
- Alle Seiten öffnen, keine Tracebacks sehen.
- SCT/MCT immer als ganze Sekunden angezeigt.
- Laufzeiten bleiben Hundertstel-genau, Zeitfehler = Laufzeit − SCT.
- DIS nur, wenn Laufzeit > MCT.
