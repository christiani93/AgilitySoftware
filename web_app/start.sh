#!/usr/bin/env bash
# start_dev.sh
# - Kein Git-Update
# - Python sicherstellen (brew/apt/pyenv, best effort), venv anlegen, requirements installieren/aktualisieren
# - Start im Dev-Mode (abschaltbar mit --no-run)

set -euo pipefail

NO_RUN=0
if [[ "${1:-}" == "--no-run" ]]; then
  NO_RUN=1
fi

echo "=== AgilitySoftware :: start_dev (Unix) ==="

# 1) Git NICHT anfassen
echo "Git bleibt unverändert (kein fetch/pull)."

# 2) Python sicherstellen
have_py() { command -v python3 >/dev/null 2>&1; }
if ! have_py; then
  echo "Python3 nicht gefunden. Versuche Installation..." >&2
  if command -v brew >/dev/null 2>&1; then
    brew install python
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-venv python3-pip
  else
    echo "Kein bekannter Paketmanager gefunden. Bitte Python3 manuell installieren." >&2
    exit 1
  fi
fi

# 3) venv
if [[ ! -d ".venv" ]]; then
  echo "Erzeuge virtuelles Environment (.venv)..."
  python3 -m venv .venv
fi

# 4) aktivieren & Pip aktualisieren
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel

# 5) Requirements
if [[ -f "requirements.txt" ]]; then
  echo "Installiere/aktualisiere Requirements..."
  pip install -r requirements.txt --upgrade
else
  echo "Warnung: requirements.txt nicht gefunden – überspringe Paketinstallation."
fi

# 6) Dev-Start
if [[ "$NO_RUN" -eq 0 ]]; then
  export FLASK_ENV=development
  export PYTHONUNBUFFERED=1
  echo "Starte App..."

  if [[ -f "app.py" ]]; then
    python app.py
  elif [[ -f "wsgi.py" ]]; then
    python wsgi.py
  else
    echo "Kein app.py/wsgi.py gefunden. Starte: flask --app app run"
    flask --app app run --reload
  fi
else
  echo "Setup fertig. (--no-run gesetzt, daher kein Start der Anwendung.)"
fi
