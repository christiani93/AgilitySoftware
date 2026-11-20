from flask_socketio import SocketIO
# Zentraler SocketIO-Container, um Zirkularimporte zu vermeiden.
# async_mode explizit auf 'threading' fixiert: ohne das versucht engineio beim
# Start, eventlet/gevent/gevent_uwsgi/threading per Laufzeit-Import
# (importlib.import_module mit zusammengesetztem Modulnamen) der Reihe nach
# durchzuprobieren. In der PyInstaller-EXE sieht die statische Analyse diese
# Laufzeit-Imports nicht, keines der Module wird gebuendelt → ALLE Versuche
# schlagen fehl → "ValueError: Invalid async_mode specified" direkt beim Start
# (Crash 2026-11-20, dist/app.exe + dist/AgilitySoftware.exe betroffen).
# 'threading' ist fuer diese Desktop-App (ein Prozess, kein Reactor noetig)
# ausreichend; der zugehoerige Treiber wird unten (siehe app.py) zusaetzlich
# statisch importiert, damit PyInstaller ihn sicher mitbuendelt.
socketio = SocketIO(async_mode='threading')
