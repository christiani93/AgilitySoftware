📘 AgilitySoftware – Startanleitung für Turniertage (aktualisiert 2025)

Diese Anleitung beschreibt den Start der AgilitySoftware mit dem neuen Launcher, inklusive der automatischen Erzeugung aller Ring-Skripte mit Python-venv und dem produktiven Start der Zeitnahme.

📁 Ordnerstruktur

Der Hauptordner enthält:

AgilitySoftware\
 ├── Start_Launcher.bat
 ├── Start_AgilitySoftware.bat
 ├── Start_Ring_1.bat
 ├── Start_Ring_2.bat
 ├── Start_Ring_3.bat
 ├── Start_Ring_dev.bat
 └── web_app\
      ├── app.py (Webserver)
      ├── ring_server\
      ├── flask_env\
      └── ring_env\

⚙️ 1. Einmalige Einrichtung / Vorbereitung
📌 1.1 Server-IP setzen

Start_Launcher.bat starten

Menüpunkt [S] Server-IP setzen wählen

IP eingeben:

DEV: 127.0.0.1

PROD (Turniertag): IP des Server-PCs, z. B.:

192.168.0.10


Der Launcher erzeugt dann Start_Ring_1/2/3.bat neu:

jeweils mit korrekter Server-IP

mit venv-Erstellung für Python 32-bit

mit Paketinstallation für Ringserver

Wenn du die IP änderst → [S] erneut ausführen.

🖥️ 2. Start des Webservers (Hauptsystem)

Auf dem Server-PC:

Start_Launcher.bat starten

Menüpunkt [1] Hauptsystem starten

Ein neues Fenster „Agility Main“ öffnet sich und führt aus:

venv-Prüfung flask_env

Installation/Update der Webserver-Pakete

Start von app.py (Flask Webserver)

Sobald der Webserver läuft, öffnet sich ein Browser auf:

http://localhost:5000


Dort befindet sich die komplette Weboberfläche.

🐕‍🦺 3. Start der Ringe

Je Ring-PC:

Start_Launcher.bat im AgilitySoftware-Ordner öffnen
(kann auch über ein Netzlaufwerk wie Z:\AgilitySoftware sein)

Menüpunkt auswählen:

[2] Ring 1 starten

[3] Ring 2 starten

[4] Ring 3 starten

Für jeden Ring öffnet sich EIN neues Fenster:

Ring X (venv)
[RINGX] Verwende Python 32-bit ...
[RINGX] Prüfe virtuelle Umgebung ...
[RINGX] Erstelle venv (falls nötig) ...
[RINGX] Aktualisiere Pakete ...
[RINGX] Starte Ring-Server ...
Running on http://127.0.0.1:500X


Dieses Fenster muss während des gesamten Turniers geöffnet bleiben.

🔧 4. DEV-Ring (Testmodus)

Für Tests in der Entwicklung:

Start_Launcher.bat

Menüpunkt [D]

Ein neues Fenster öffnet Start_Ring_dev.bat:

eigene venv

lokale IP

Vollausgabe der Pakete

Ideal für Prototypen und Debugging, unabhängig vom Live-Betrieb.

🌐 5. Ring-PC Browser-Ansicht öffnen

Auf jedem Ring-PC zusätzlich im Browser:

http://SERVER-IP:5000/ring_pc_dashboard/X


Beispiele:

Ring 1:

http://192.168.0.10:5000/ring_pc_dashboard/1


Ring 2:

http://192.168.0.10:5000/ring_pc_dashboard/2


Ring 3:

http://192.168.0.10:5000/ring_pc_dashboard/3

🧪 6. Automatisches Setup: venv für Ringe

Jedes Start_Ring_X-Skript erledigt:

Anlegen der 32-bit-venv (ring_env)

Installation/Update aller Pakete:

Flask

Flask-SocketIO

Requests

pywin32

Start des Ring-Servers für ring_server.py

👉 Du musst als Benutzer NICHTS manuell installieren.

🔍 7. Troubleshooting
🟥 Ring startet nicht, Meldung „FEHLER: ring_env konnte nicht erstellt werden“

→ einmalig:

Start_Ring_dev.bat


laufen lassen, danach Ring normal starten.

🟥 Webserver geht nicht auf

→ Start_AgilitySoftware.bat erneut starten
→ prüfen, ob Port 5000 frei ist
→ Browser aufrufen:

http://localhost:5000

🟥 Python 32-bit fehlt

→ Launcher [C] → Python-Check
→ Installer installieren:
https://www.python.org/downloads/windows/

🟥 Falsche Ring-IP

→ Launcher [S] → IP neu setzen → Skripte werden aktualisiert.

🏁 8. Typischer Start am Turniertag
Auf dem Server-PC:

Start_Launcher.bat

[S] Server-IP prüfen/setzen

[1] Hauptsystem starten

Auf jedem Ring-PC:

Ordner öffnen (Server via Netzlaufwerk oder lokale Kopie)

Start_Launcher.bat

Ring auswählen:

[2] Ring 1

[3] Ring 2

[4] Ring 3

Ring-PC-Dashboard im Browser öffnen

🎉 Fertig!

Alle Systeme laufen unabhängig voneinander in eigenen Fenstern:

1 Hauptsystem für Wettbewerbsverwaltung

X Ringserver für Zeitnahme

X Ring-PC Dashboards im Browser

Stabil, autark, offline-fähig