"""Live-Status-Fenster für den Ring-Server.

Wird vom :mod:`ring_launcher` nach der Konfiguration geöffnet und zeigt:

  - Ring-Identität (Label, Nr, Listen-Port, Hauptserver-IP)
  - Aktueller Status (idle / ready / running / finished_timing)
  - Aktueller Starter (Startnummer + Name, sofern vom Hauptserver gesetzt)
  - Schleppzeit (live tickend, sobald TIMY den Start-Impuls bekommen hat)
  - Fehler- und Verweigerungs-Zähler

Der Tk-Mainloop läuft im Hauptthread; der eigentliche SocketIO-Server
läuft im Hintergrund-Thread. Beim Schließen des Fensters wird der Prozess
beendet (über ``os._exit``, damit der SocketIO-Thread nicht hängen bleibt).

Die Anzeige liest direkt das ``state``-Dict aus :mod:`ring_server` (es wird
beim Konstruktor übergeben). Damit ist die Anzeige eine reine View –
keine zusätzliche Synchronisation nötig.
"""
from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import ttk


# Farbschema je Status
_STATUS_COLORS = {
    "idle":            ("#777777", "Idle"),
    "ready":           ("#1976D2", "Bereit"),
    "running":         ("#2E7D32", "Lauf"),
    "finished_timing": ("#F57C00", "Fertig"),
}


class RingDashboard:
    """Tkinter-Fenster mit Live-Status."""

    def __init__(self, state_ref, ring_label: str, ring_number: int,
                 listen_port: int, server_ip: str, server_port: int,
                 timy_available: bool):
        self.state = state_ref
        self.ring_label = ring_label
        self.ring_number = ring_number
        self.listen_port = listen_port
        self.server_ip = server_ip
        self.server_port = server_port
        self.timy_available = timy_available

        # Anker zur Berechnung der Schleppzeit (monotonic-basiert, weil
        # TIMY-Zeit als Time-of-Day-String vorliegt und Tag-Übergänge tricky sind).
        self._run_start_monotonic: float | None = None

        self.root = tk.Tk()
        self.root.title(f"{ring_label} - Status")

        self._build_widgets()

        # Tk soll erst die natürliche Wunschgröße aus den Widgets berechnen,
        # dann setzen wir geometry() darauf -> alle Felder ohne Scrollen sichtbar.
        self.root.update_idletasks()
        w = max(480, self.root.winfo_reqwidth())
        h = max(560, self.root.winfo_reqheight())
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(w, h)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll)

    def _build_widgets(self):
        # Style fuer grosse Status-Zahlen
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)

        # --- Kopfzeile: Ring-Info ---
        head = ttk.LabelFrame(main, text="Ring", padding=8)
        head.grid(row=0, column=0, columnspan=2, sticky="ew")
        head.columnconfigure(1, weight=1)

        ttk.Label(head, text=f"{self.ring_label}  (Nr. {self.ring_number})",
                  font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        timy_text = "TIMY verbunden" if self.timy_available else "kein TIMY"
        timy_color = "#2E7D32" if self.timy_available else "#C62828"
        ttk.Label(head, text=timy_text, foreground=timy_color).grid(row=0, column=1, sticky="e")
        ttk.Label(head, text=f"Listen-Port  {self.listen_port}",
                  foreground="#666").grid(row=1, column=0, sticky="w")
        ttk.Label(head, text=f"Hauptserver  {self.server_ip}:{self.server_port}",
                  foreground="#666").grid(row=1, column=1, sticky="e")

        # Hauptserver-Heartbeat-Status (eigene Zeile, zentriert)
        self.server_status_var = tk.StringVar(value="Hauptserver: prüfe ...")
        self.server_status_label = tk.Label(head, textvariable=self.server_status_var,
                                            font=("Segoe UI", 9, "bold"),
                                            fg="#888")
        self.server_status_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        # --- Status (gross) ---
        st = ttk.LabelFrame(main, text="Status", padding=8)
        st.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        st.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="—")
        self.status_label = tk.Label(st, textvariable=self.status_var,
                                     font=("Segoe UI", 22, "bold"),
                                     fg="#777")
        self.status_label.grid(row=0, column=0, sticky="ew")

        self.starter_var = tk.StringVar(value="kein Starter")
        ttk.Label(st, textvariable=self.starter_var,
                  font=("Segoe UI", 10), foreground="#444").grid(row=1, column=0, sticky="ew")

        # --- Zeit ---
        zt = ttk.LabelFrame(main, text="Schleppzeit", padding=8)
        zt.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        zt.columnconfigure(0, weight=1)
        self.time_var = tk.StringVar(value="—")
        self.time_label = tk.Label(zt, textvariable=self.time_var,
                                   font=("Consolas", 28, "bold"),
                                   fg="#1A237E")
        self.time_label.grid(row=0, column=0, sticky="ew")

        # --- Zaehler ---
        cnt = ttk.Frame(main)
        cnt.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        cnt.columnconfigure(0, weight=1)
        cnt.columnconfigure(1, weight=1)

        def _counter(parent, title, var):
            f = ttk.LabelFrame(parent, text=title, padding=6)
            tk.Label(f, textvariable=var, font=("Segoe UI", 20, "bold"),
                     fg="#B71C1C").pack(fill="x")
            return f

        self.faults_var = tk.StringVar(value="0")
        self.refusals_var = tk.StringVar(value="0")
        _counter(cnt, "Fehler", self.faults_var).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        _counter(cnt, "Verweigerungen", self.refusals_var).grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _format_starter(self) -> str:
        s = self.state.get("current_starter") or {}
        if not s:
            return "kein Starter"
        sn = s.get("Startnummer") or s.get("startnummer") or "?"
        name = s.get("Hundefuehrer") or s.get("hundefuehrer") or ""
        hund = s.get("Hundename") or s.get("hundename") or ""
        parts = [str(sn)]
        if name:
            parts.append(str(name))
        if hund:
            parts.append(f"/ {hund}")
        return "  ".join(parts).strip()

    def _poll(self):
        try:
            st = self.state
            status = (st.get("run_status") or "idle").lower()

            color, label = _STATUS_COLORS.get(status, ("#777", status.upper()))
            self.status_var.set(label)
            self.status_label.configure(fg=color)

            self.starter_var.set(self._format_starter())
            self.faults_var.set(str(st.get("faults", 0)))
            self.refusals_var.set(str(st.get("refusals", 0)))

            # Hauptserver-Verbindungsstatus
            reachable = bool(st.get("server_reachable"))
            last = float(st.get("server_last_check") or 0.0)
            if last <= 0:
                self.server_status_var.set("Hauptserver: prüfe ...")
                self.server_status_label.configure(fg="#888")
            elif reachable:
                self.server_status_var.set(
                    f"Hauptserver verbunden  ({self.server_ip}:{self.server_port})"
                )
                self.server_status_label.configure(fg="#2E7D32")
            else:
                self.server_status_var.set(
                    f"Hauptserver NICHT erreichbar  ({self.server_ip}:{self.server_port})"
                )
                self.server_status_label.configure(fg="#C62828")

            if status == "running":
                if self._run_start_monotonic is None:
                    self._run_start_monotonic = time.monotonic()
                elapsed = time.monotonic() - self._run_start_monotonic
                self.time_var.set(f"{elapsed:5.2f}")
                self.time_label.configure(fg="#2E7D32")
            elif status == "finished_timing":
                ft = st.get("final_time")
                if ft is not None:
                    self.time_var.set(f"{float(ft):5.2f}")
                self.time_label.configure(fg="#F57C00")
            else:
                # idle / ready / unknown
                self._run_start_monotonic = None
                if status == "ready":
                    self.time_var.set(" 0.00")
                    self.time_label.configure(fg="#1976D2")
                else:
                    self.time_var.set("—")
                    self.time_label.configure(fg="#888")
        finally:
            # Auch bei Exception weiter pollen (View darf nie sterben)
            self.root.after(100, self._poll)

    def run(self):
        self.root.mainloop()

    def _on_close(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        # Hartes Ende, damit Hintergrund-Threads (Flask/SocketIO/TIMY) nicht hängen
        os._exit(0)
