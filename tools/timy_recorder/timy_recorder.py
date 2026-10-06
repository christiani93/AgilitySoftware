"""Standalone TIMY-Recorder — eigenständig, OHNE AgilitySoftware/Flask.

Zweck
-----
Zeichnet die Rohdaten eines ALGE-TIMY über die USB-Schnittstelle auf, um

  1. die TIMY-Zeitberechnung zu verifizieren — jede C0->C1-Rechnung wird gegen
     die vom TIMY selbst gesendete RT-Zeile (= Wert auf der Anzeigetafel)
     geprueft, und
  2. die "Zeit zwischen 2 Starts" zu messen (Abstand aufeinanderfolgender
     C0-Impulse in Tageszeit) — Datengrundlage fuer die Zeitplan-Optimierung
     im AgilityPortal.

Das Tool hat KEINE Abhaengigkeit zur AgilitySoftware: kein Flask, kein
SocketIO, kein requests, kein events.json. Nur pywin32 (fuer die echte
TIMY-Anbindung). Die Kernlogik (TimyRecorder) laeuft komplett ohne Hardware
und ist ueber --replay / --simulate testbar.

Erkannte TIMY-Zeilenformate (aus echten Aufnahmen)
--------------------------------------------------
  '0006 C0  13:20:16.0431 00'   Start   (Kanal C0 oder C0M)
  '0006 C1  13:20:21.0159 00'   Stop    (Kanal C1 oder C1M)
  '0006 RT  00:00:04.97   00'   Laufzeit laut TIMY (= Anzeigetafel; RT/RTM)
  '?0001 C1M 13:17:01.71  00'   vom TIMY nachtraeglich korrigierter Impuls ('?')
  'TIMY: 480170000'             laufende Uhr (Rauschen, wird ignoriert)
  'n0007' / 's0008'             Status-Marker (nur geloggt)

WICHTIG — Pairing: Start/Stop/RT tragen eine fuehrende LAUF-NUMMER. Das TIMY
kann mehrere Zeiten gleichzeitig laufen lassen (mehrere Hunde gestartet, bevor
der erste im Ziel ist) und paart C0/C1 ueber genau diese Nummer. Der Recorder
muss daher pro Lauf-Nummer paaren — ein einzelner Slot wuerde bei
ueberlappenden Starts falsch zuordnen.

Ausgaben (neben dieser Datei bzw. --log-dir):
  timy_record_<ring>_<YYYYMMDD_HHMMSS>.log   Mensch-lesbar: Ereignisse + Rechnung
  timy_record_<ring>_<YYYYMMDD_HHMMSS>.csv   Strukturiert: eine Zeile pro Lauf

CSV-Spalten:
  idx, run_no, start_tod, stop_tod, raw_diff_s, final_time_s,
  timy_rt_s, delta_vs_timy_s, start_interval_s, flags
    idx               laufende Nummer des Starts (Reihenfolge der C0)
    run_no            Lauf-Nummer des TIMY (Pairing-Schluessel)
    start_tod         Tageszeit C0 (HH:MM:SS.ffff)
    stop_tod          Tageszeit C1 (leer, falls kein Stop)
    raw_diff_s        stop_s - start_s (ungerundet)
    final_time_s      final_time nach floor auf 0.01 (wie AgilitySoftware)
    timy_rt_s         Laufzeit laut TIMY-RT-Zeile (Anzeigetafel)
    delta_vs_timy_s   final_time_s - timy_rt_s (sollte 0.00 sein)
    start_interval_s  Sekunden seit dem vorherigen C0 ("Zeit zwischen 2 Starts")
    flags             z.B. no_c1 / no_start / rt_only / corrected
"""
from __future__ import annotations

import argparse
import datetime
import math
import os
import re
import sys
import time

# ---------------------------------------------------------------------------
# Parsing / Zeitrechnung
# ---------------------------------------------------------------------------
# Impuls- UND RT-Zeilen: optionales '?', Lauf-Nummer, Kanal, Zeit(HH:MM:SS.frac).
_LINE_RE = re.compile(r'^\s*(\?)?\s*(\d+)\s+([A-Za-z]\w*)\s+(\d{2}:\d{2}:\d{2}\.\d+)')
# Laufende Uhr des TIMY (Rauschen): 'TIMY: 480170000'
_HEARTBEAT_RE = re.compile(r'^\s*TIMY:\s*\d+\s*$')


def parse_timy_output(line: str):
    """Zerlegt eine TIMY-Zeile.

    Rueckgabe dict | None:
      {'kind': 'start'|'stop'|'timy_rt'|'other',
       'channel', 'run_no', 'time_of_day', 'corrected': bool}
    """
    m = _LINE_RE.match(line)
    if not m:
        return None
    corrected = bool(m.group(1))
    run_no = m.group(2)
    channel = m.group(3)
    tod = m.group(4)
    up = channel.upper()
    if up.startswith('C0'):
        kind = 'start'
    elif up.startswith('C1'):
        kind = 'stop'
    elif up.startswith('RT'):
        kind = 'timy_rt'
    else:
        kind = 'other'
    return {'kind': kind, 'channel': channel, 'run_no': run_no,
            'time_of_day': tod, 'corrected': corrected}


def time_str_to_seconds(time_str: str) -> float:
    """HH:MM:SS.frac -> Sekunden. Funktioniert fuer Tageszeit UND fuer die
    RT-Dauer (00:00:SS.ss)."""
    if not time_str:
        return 0.0
    try:
        parts = time_str.split(':')
        h, m = int(parts[0]), int(parts[1])
        s_parts = parts[2].split('.')
        s = int(s_parts[0])
        frac_s = int(s_parts[1]) / (10 ** len(s_parts[1])) if len(s_parts) > 1 else 0
        return (h * 3600) + (m * 60) + s + frac_s
    except (ValueError, IndexError, TypeError):
        return 0.0


def floor_hundredths(diff_s: float) -> float:
    """final_time wie AgilitySoftware: auf Hundertstel ABSCHNEIDEN, nicht runden.
    Epsilon schuetzt gegen Float-Ungenauigkeit (z.B. 35.68*100 = 3567.9999...)."""
    return math.floor(diff_s * 100 + 1e-9) / 100


# ---------------------------------------------------------------------------
# Kern-Rekorder — hardware-unabhaengig, vollstaendig testbar
# ---------------------------------------------------------------------------
class TimyRecorder:
    """Verarbeitet rohe TIMY-Zeilen, schreibt .log + .csv und gibt Live-Infos
    auf die Konsole aus. Enthaelt keinerlei COM-/Flask-Bezug.

    Pairing ueber die Lauf-Nummer (run_no): offene Starts liegen in
    ``open_starts``; beim C1 wird der passende Start herausgesucht, das Ergebnis
    in ``pending_finish`` geparkt und erst mit der RT-Zeile (Vergleich
    berechnet<->TIMY) final in die CSV geschrieben. Ohne RT wird spaetestens
    beim naechsten C0 derselben Nummer bzw. beim close() geflusht.
    """

    CSV_HEADER = ("idx,run_no,start_tod,stop_tod,raw_diff_s,final_time_s,"
                  "timy_rt_s,delta_vs_timy_s,start_interval_s,flags\n")

    def __init__(self, ring: str = "ring", log_dir: str | None = None, echo=print):
        self.ring = ring
        self.echo = echo
        ring_tag = re.sub(r"[^A-Za-z0-9_-]+", "_", ring) or "ring"
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = log_dir or os.path.dirname(os.path.abspath(__file__))
        os.makedirs(base, exist_ok=True)
        self.log_path = os.path.join(base, f"timy_record_{ring_tag}_{stamp}.log")
        self.csv_path = os.path.join(base, f"timy_record_{ring_tag}_{stamp}.csv")

        # Zustand
        self.open_starts: dict[str, dict] = {}     # run_no -> {idx, start_tod, interval}
        self.pending_finish: dict[str, dict] = {}   # run_no -> berechneter Lauf (wartet auf RT)
        self.prev_start_tod: str | None = None       # letzter C0 nach Zeit (fuer Intervall)
        self.idx = 0
        self.heartbeats = 0

        self._log_fh = open(self.log_path, "a", encoding="utf-8")
        self._csv_fh = open(self.csv_path, "a", encoding="utf-8")
        self._csv_fh.write(self.CSV_HEADER)
        self._csv_fh.flush()

        self._log(f"=== TIMY-Recorder gestartet — Ring {ring!r} — {stamp} ===")
        self.echo(f"Log : {self.log_path}")
        self.echo(f"CSV : {self.csv_path}")

    # -- interne Helfer ----------------------------------------------------
    def _log(self, text: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        try:
            self._log_fh.write(f"[{ts}] {text}\n")
            self._log_fh.flush()
        except Exception:
            pass

    def _csv_row(self, rec: dict) -> None:
        def f(x):
            return "" if x is None else (f"{x:.4f}" if isinstance(x, float) else str(x))
        try:
            self._csv_fh.write(
                f"{f(rec.get('idx'))},{rec.get('run_no') or ''},"
                f"{rec.get('start_tod') or ''},{rec.get('stop_tod') or ''},"
                f"{f(rec.get('raw_diff'))},{f(rec.get('final_time'))},"
                f"{f(rec.get('timy_rt'))},{f(rec.get('delta'))},"
                f"{f(rec.get('interval'))},{rec.get('flags') or ''}\n"
            )
            self._csv_fh.flush()
        except Exception:
            pass

    @staticmethod
    def _add_flag(rec: dict, flag: str) -> None:
        cur = rec.get('flags') or ''
        rec['flags'] = f"{cur}|{flag}" if cur else flag

    # -- Haupteinstieg: eine rohe TIMY-Zeile ------------------------------
    def handle_line(self, line: str) -> None:
        line = (line or "").strip()
        if not line:
            return
        if _HEARTBEAT_RE.match(line):
            self.heartbeats += 1                     # laufende Uhr: nur zaehlen
            return
        parsed = parse_timy_output(line)
        if not parsed:
            self._log(f"raw={line!r} | MARKER/UNMATCHED")
            return

        corr = " [KORREKTUR '?']" if parsed['corrected'] else ""
        self._log(f"raw={line!r} | run={parsed['run_no']} ch={parsed['channel']} "
                  f"kind={parsed['kind']} tod={parsed['time_of_day']}{corr}")

        if parsed['kind'] == 'start':
            self._on_start(parsed)
        elif parsed['kind'] == 'stop':
            self._on_stop(parsed)
        elif parsed['kind'] == 'timy_rt':
            self._on_timy_rt(parsed)

    def _on_start(self, p: dict) -> None:
        run_no, tod = p['run_no'], p['time_of_day']
        self.idx += 1
        interval = None
        if self.prev_start_tod:
            delta = time_str_to_seconds(tod) - time_str_to_seconds(self.prev_start_tod)
            if delta > 0:                            # negativ = Mitternacht/Fehlimpuls
                interval = delta
        if run_no in self.open_starts:
            self._log(f"  >> HINWEIS: Lauf {run_no} hatte bereits einen offenen Start — ueberschrieben.")
        self.open_starts[run_no] = {
            "idx": self.idx, "start_tod": tod, "interval": interval,
            "flags": "corrected" if p['corrected'] else "",
        }
        self.prev_start_tod = tod
        iv = f"{interval:.3f}s seit letztem Start" if interval is not None else "erster Start"
        self._log(f"  >> START #{self.idx} Lauf {run_no} tod={tod}  ({iv})")
        self.echo(f"[{self.ring}] START #{self.idx} Lauf {run_no}  {tod}   Intervall: {iv}")

    def _on_stop(self, p: dict) -> None:
        run_no, tod = p['run_no'], p['time_of_day']
        start = self.open_starts.pop(run_no, None)
        if start is None:
            self._log(f"  >> HINWEIS: C1 Lauf {run_no} ({tod}) ohne passenden offenen Start — als rt_only vermerkt.")
            self.echo(f"[{self.ring}] STOP Lauf {run_no} ohne Start — warte auf RT ({tod})")
            # Platzhalter, damit eine evtl. folgende RT-Zeile trotzdem erfasst wird.
            self.pending_finish[run_no] = {
                "idx": None, "run_no": run_no, "start_tod": None, "stop_tod": tod,
                "raw_diff": None, "final_time": None, "interval": None, "flags": "no_start",
            }
            return
        start_s = time_str_to_seconds(start["start_tod"])
        stop_s = time_str_to_seconds(tod)
        raw_diff = stop_s - start_s
        rec = {
            "idx": start["idx"], "run_no": run_no, "start_tod": start["start_tod"],
            "stop_tod": tod, "interval": start["interval"], "flags": start.get("flags") or "",
        }
        if p['corrected']:
            self._add_flag(rec, "corrected")
        if not (start_s > 0 and stop_s > start_s):
            self._log(f"  >> FEHLER: ungueltige Zeit (start_s={start_s} stop_s={stop_s}).")
            rec.update(raw_diff=None, final_time=None)
            self._add_flag(rec, "invalid")
        else:
            final_time = floor_hundredths(raw_diff)
            rec.update(raw_diff=raw_diff, final_time=final_time)
            self._log(
                f"  >> BERECHNUNG: Lauf {run_no} start={start['start_tod']!r} stop={tod!r} "
                f"raw_diff={raw_diff!r} -> final_time={final_time!r} (warte auf RT-Vergleich)"
            )
            self.echo(f"[{self.ring}] STOP  Lauf {run_no}  Zeit={final_time:.2f}s  (roh {raw_diff:.4f})")
        self.pending_finish[run_no] = rec

    def _on_timy_rt(self, p: dict) -> None:
        run_no = p['run_no']
        timy_rt = time_str_to_seconds(p['time_of_day'])
        rec = self.pending_finish.pop(run_no, None)
        if rec is None:
            # RT ohne vorherigen C1 bei uns — TIMY-Wert trotzdem festhalten.
            rec = {"idx": None, "run_no": run_no, "start_tod": None, "stop_tod": None,
                   "raw_diff": None, "final_time": None, "interval": None, "flags": "rt_only"}
        rec["timy_rt"] = timy_rt
        if rec.get("final_time") is not None:
            delta = round(rec["final_time"] - timy_rt, 4)
            rec["delta"] = delta
            flag = "OK" if abs(delta) < 1e-9 else f"ABWEICHUNG {delta:+.2f}s"
            self._log(f"  >> RT-VERGLEICH Lauf {run_no}: berechnet={rec['final_time']:.2f} "
                      f"TIMY={timy_rt:.2f}  delta={delta:+.4f}  [{flag}]")
            if abs(delta) >= 1e-9:
                self.echo(f"[{self.ring}] !! Lauf {run_no}: berechnet {rec['final_time']:.2f} "
                          f"vs TIMY {timy_rt:.2f}  (delta {delta:+.2f})")
        else:
            self._log(f"  >> RT Lauf {run_no}: TIMY={timy_rt:.2f} (keine eigene Berechnung vorhanden).")
        self._csv_row(rec)

    def close(self) -> None:
        # Laeufe mit C1 aber ohne RT: mit dem Berechneten festhalten.
        for run_no, rec in list(self.pending_finish.items()):
            self._add_flag(rec, "no_rt")
            self._csv_row(rec)
            self.pending_finish.pop(run_no, None)
        # Starts ohne C1: Intervall trotzdem festhalten.
        for run_no, start in list(self.open_starts.items()):
            self._csv_row({
                "idx": start["idx"], "run_no": run_no, "start_tod": start["start_tod"],
                "stop_tod": None, "raw_diff": None, "final_time": None,
                "timy_rt": None, "delta": None, "interval": start["interval"],
                "flags": (start.get("flags") + "|no_c1").strip("|") if start.get("flags") else "no_c1",
            })
        self._log(f"=== Recorder beendet (laufende-Uhr-Zeilen ignoriert: {self.heartbeats}) ===")
        for fh in (self._log_fh, self._csv_fh):
            try:
                fh.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Echte TIMY-Anbindung (pywin32 / ALGE-USB) — nur wenn Hardware vorhanden
# ---------------------------------------------------------------------------
def run_hardware(recorder: TimyRecorder) -> int:
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        print("!! FEHLER: pywin32 nicht verfuegbar. Bitte im 32-bit 'ring_env' "
              "starten (web_app\\ring_env) oder --replay/--simulate nutzen.")
        return 2

    class _Events:
        def OnConnectionOpen(self):
            print(">> Verbindung zum TIMY offen. Warte auf Impulse … (Strg+C beendet)")

        def OnUSBInput(self, data):
            try:
                recorder.handle_line(data)
            except Exception as e:
                print(f"!! Fehler bei Zeile {data!r}: {e}")

    pythoncom.CoInitialize()
    conn = None
    try:
        conn = win32com.client.DispatchWithEvents('ALGEUSB.TimyUSB', _Events)
        conn.Init()
        conn.OpenConnection(0)
        while True:
            pythoncom.PumpWaitingMessages()
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n>> Beende (Strg+C).")
        return 0
    except Exception as e:
        print(f"!! TIMY-FEHLER: {e}")
        return 1
    finally:
        if conn is not None:
            try:
                conn.CloseConnection()
            except Exception:
                pass
        pythoncom.CoUninitialize()


# ---------------------------------------------------------------------------
# Test-/Offline-Modi (ohne Hardware)
# ---------------------------------------------------------------------------
def run_replay(recorder: TimyRecorder, path: str) -> int:
    """Spielt eine Datei mit je einer rohen TIMY-Zeile pro Zeile durch.
    Akzeptiert auch die .log dieses Recorders: extrahiert das raw='…'."""
    if not os.path.isfile(path):
        print(f"!! Replay-Datei nicht gefunden: {path}")
        return 2
    raw_re = re.compile(r"raw='(.*?)'\s*\|")
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = raw_re.search(line)
            recorder.handle_line(m.group(1) if m else line)
    print(">> Replay fertig.")
    return 0


def run_simulate(recorder: TimyRecorder, n: int = 5) -> int:
    """Erzeugt n synthetische Laeufe (inkl. RT-Zeile) mit plausiblen Werten."""
    import random
    t = datetime.datetime.now().replace(microsecond=0)
    for i in range(n):
        run_no = f"{i+1:04d}"
        start = t
        run_s = random.uniform(28.0, 45.0)
        stop = start + datetime.timedelta(seconds=run_s)
        final = floor_hundredths(run_s)
        st = f"{start.strftime('%H:%M:%S')}.{random.randint(0,9999):04d}"
        sp = f"{stop.strftime('%H:%M:%S')}.{random.randint(0,9999):04d}"
        recorder.handle_line(f"{run_no} C0  {st} 00")
        recorder.handle_line(f"{run_no} C1  {sp} 00")
        recorder.handle_line(f"{run_no} RT  00:00:{final:05.2f}   00")
        t = stop + datetime.timedelta(seconds=random.uniform(15.0, 30.0))
    print(">> Simulation fertig.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Standalone TIMY-Recorder (ohne AgilitySoftware).")
    p.add_argument("--ring", default="ring", help="Ring-Label fuer die Dateinamen (z.B. 'Ring 1').")
    p.add_argument("--log-dir", default=None, help="Zielordner fuer .log/.csv (Default: neben diesem Skript).")
    p.add_argument("--replay", default=None, help="Rohe TIMY-Zeilen (oder eine .log) einspielen (Test ohne Hardware).")
    p.add_argument("--simulate", type=int, nargs="?", const=5, default=None,
                   help="N synthetische Laeufe erzeugen (Test ohne Hardware).")
    args = p.parse_args(argv)

    recorder = TimyRecorder(ring=args.ring, log_dir=args.log_dir)
    try:
        if args.replay is not None:
            return run_replay(recorder, args.replay)
        if args.simulate is not None:
            return run_simulate(recorder, args.simulate)
        print(f">> Hardware-Modus. Ring={args.ring!r}. Verbinde mit TIMY …")
        return run_hardware(recorder)
    finally:
        recorder.close()


if __name__ == "__main__":
    sys.exit(main())
