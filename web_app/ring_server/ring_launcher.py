"""Ring-Server-Launcher mit kleinem Tkinter-UI.

Beim Start öffnet sich ein Fenster zur Auswahl von Ring-Nummer und
Hauptserver-IP. Die Auswahl wird in ``ring_config.json`` neben der EXE
gespeichert und beim nächsten Start vorausgefüllt.

Port-Konvention: ``Port = 5000 + Ring-Nr`` (Ring 1 -> 5001, Ring 2 -> 5002, ...).
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tkinter as tk
from tkinter import messagebox, ttk


def _config_path() -> str:
    """Speicherort der Ring-Config. Bei PyInstaller-Bundle: neben der EXE."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "ring_config.json")


def load_config() -> dict:
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(cfg: dict) -> None:
    try:
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"WARNUNG: ring_config.json konnte nicht gespeichert werden: {e}")


def _suggest_server_ip() -> str:
    """Schlägt eine sinnvolle Default-Server-IP vor (eigene LAN-IP).

    Annahme: Der Ring-Server läuft im selben Subnetz wie der Hauptserver.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        parts = ip.split(".")
        if len(parts) == 4:
            parts[3] = "10"
            return ".".join(parts)
    except Exception:
        pass
    return "192.168.1.10"


class RingLauncherUI:
    def __init__(self, root: tk.Tk, cfg: dict):
        self.root = root
        self.cfg = cfg
        self.result = None

        root.title("AgilityRing - Launcher")
        root.geometry("420x280")
        root.resizable(False, False)

        main = ttk.Frame(root, padding=16)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="AgilityRing-Server starten",
                  font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Label(main, text="Ring-Nummer:").grid(row=1, column=0, sticky="w", pady=4)
        self.ring_var = tk.IntVar(value=int(cfg.get("ring_number", 1)))
        ring_frame = ttk.Frame(main)
        ring_frame.grid(row=1, column=1, sticky="w")
        for n in (1, 2, 3):
            ttk.Radiobutton(ring_frame, text=f"Ring {n}", variable=self.ring_var,
                            value=n, command=self._update_port_label).pack(side="left", padx=4)

        ttk.Label(main, text="Hauptserver-IP:").grid(row=2, column=0, sticky="w", pady=4)
        self.ip_var = tk.StringVar(value=cfg.get("server_ip") or _suggest_server_ip())
        ttk.Entry(main, textvariable=self.ip_var, width=24).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(main, text="Hauptserver-Port:").grid(row=3, column=0, sticky="w", pady=4)
        self.server_port_var = tk.IntVar(value=int(cfg.get("server_port", 5000)))
        ttk.Entry(main, textvariable=self.server_port_var, width=8).grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(main, text="Eigener Port:").grid(row=4, column=0, sticky="w", pady=4)
        self.port_label = ttk.Label(main, text="", foreground="#444")
        self.port_label.grid(row=4, column=1, sticky="w", pady=4)
        self._update_port_label()

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=5, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(btn_frame, text="Abbrechen", command=self._cancel).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="Server starten", command=self._start).pack(side="right", padx=4)

        root.bind("<Return>", lambda e: self._start())
        root.bind("<Escape>", lambda e: self._cancel())

    def _update_port_label(self):
        port = 5000 + int(self.ring_var.get())
        self.port_label.config(text=f"{port}  (= 5000 + Ring-Nr)")

    def _start(self):
        ring_nr = int(self.ring_var.get())
        ip = self.ip_var.get().strip()
        if not ip:
            messagebox.showerror("Fehler", "Bitte Hauptserver-IP angeben.")
            return
        try:
            server_port = int(self.server_port_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Fehler", "Hauptserver-Port muss eine Zahl sein.")
            return

        self.result = {
            "ring_number": ring_nr,
            "ring_label": f"Ring {ring_nr}",
            "port": 5000 + ring_nr,
            "server_ip": ip,
            "server_port": server_port,
        }
        save_config(self.result)
        self.root.destroy()

    def _cancel(self):
        self.result = None
        self.root.destroy()


def ask_config() -> dict | None:
    cfg = load_config()
    root = tk.Tk()
    ui = RingLauncherUI(root, cfg)
    root.mainloop()
    return ui.result


RING_VERSION = "4.4"


def main():
    cfg = ask_config()
    if not cfg:
        print("Abgebrochen.")
        return 0

    # ring_server importieren (in EXE auch verfügbar)
    try:
        from ring_server import run_server
    except ImportError:
        # Fallback für Dev: Pfad zu ring_server.py auf sys.path legen
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from ring_server import run_server

    # Update-Check (non-blocking, soft-fail)
    try:
        # web_app/ auf sys.path damit updater.py gefunden wird
        web_app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if web_app_dir not in sys.path:
            sys.path.insert(0, web_app_dir)
        from updater import check_and_print
        check_and_print(RING_VERSION, component="AgilityRing")
    except Exception:
        pass

    run_server(
        ring_label=cfg["ring_label"],
        ring_number=cfg["ring_number"],
        port_num=cfg["port"],
        server_ip=cfg["server_ip"],
        server_port=cfg["server_port"],
        with_dashboard=True,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        tb = traceback.format_exc()
        print("\n!! AgilityRing konnte nicht starten:")
        print(tb)
        if getattr(sys, "frozen", False):
            try:
                from tkinter import messagebox
                messagebox.showerror("AgilityRing – Fehler",
                                     f"AgilityRing konnte nicht starten:\n\n{tb}")
            except Exception:
                pass
        raise
