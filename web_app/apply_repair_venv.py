# apply_repair_venv.py
# Baut flask_env (x64) und ring_env32 (x86) robust neu auf und prüft Aktivierung.

from pathlib import Path
import os, shutil, subprocess

ROOT = Path(__file__).parent
VENV64 = ROOT / "flask_env"
VENV32 = ROOT / "ring_env32"
REQ_MAIN = ROOT / "requirements.txt"
REQ_RING_A = ROOT / "ring_server" / "requirements.txt"
REQ_RING_B = ROOT / "requirements_ring.txt"

def run(cmd):
    print(f"[RUN] {cmd}")
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def find_py(paths):
    for p in paths:
        r = run(f'"{p}" --version')
        if r.returncode == 0:
            return p
    return None

def ensure_venv(venv, py_exe):
    act = venv / "Scripts" / "activate.bat"
    if act.exists():
        print(f"[OK] venv vorhanden: {venv}")
        return
    if venv.exists():
        print(f"[WARN] defektes venv gefunden – entferne: {venv}")
        shutil.rmtree(venv, ignore_errors=True)
    print(f"[NEW] Erzeuge venv: {venv}")
    r = run(f'"{py_exe}" -m venv "{venv}"')
    if r.returncode != 0:
        print(r.stdout, r.stderr); raise SystemExit("venv-Erstellung fehlgeschlagen.")

def install(venv, req_file, defaults):
    act = venv / "Scripts" / "activate.bat"
    if req_file and req_file.exists():
        cmd = f'cmd /c call "{act}" && python -m pip install --upgrade pip setuptools wheel && python -m pip install -r "{req_file}" --upgrade'
    else:
        pkgs = " ".join(defaults)
        cmd = f'cmd /c call "{act}" && python -m pip install --upgrade pip setuptools wheel && python -m pip install {pkgs}'
    r = run(cmd)
    if r.returncode != 0:
        print(r.stdout, r.stderr); raise SystemExit("Paketinstallation fehlgeschlagen.")
    print("[OK] Pakete installiert.")

def smoke(venv):
    act = venv / "Scripts" / "activate.bat"
    r = run(f'cmd /c call "{act}" && python -c "import flask, socketio; print(\'_SMOKE_OK_\')"')
    if "_SMOKE_OK_" not in r.stdout:
        print(r.stdout, r.stderr); raise SystemExit("Smoke-Test fehlgeschlagen.")
    print("[OK] Aktivierung/Smoke-Test ok.")

def main():
    # x64 Python bevorzugen
    py64 = find_py([
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python313\python.exe"),
        "python"
    ])
    if not py64: raise SystemExit("Kein 64-bit Python gefunden.")
    ensure_venv(VENV64, py64)
    install(VENV64, REQ_MAIN if REQ_MAIN.exists() else None,
            ["Flask", "Flask-SocketIO", "gevent", "gevent-websocket", "openpyxl", "requests"])
    smoke(VENV64)

    # x86 optional
    py32 = find_py([
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python313-32\python.exe")
    ])
    if py32:
        ensure_venv(VENV32, py32)
        req_ring = REQ_RING_A if REQ_RING_A.exists() else (REQ_RING_B if REQ_RING_B.exists() else None)
        install(VENV32, req_ring, ["pyserial"])
        print("[INFO] ring_env32 ok.")
    else:
        print("[INFO] Kein 32-bit Python gefunden – Ring_Server später.")

    print("[DONE] Venv-Reparatur abgeschlossen.")

if __name__ == "__main__":
    main()
