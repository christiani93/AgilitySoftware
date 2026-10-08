"""Diagnostischer TIMY-Mitschnitt für den Ring-Server — rein, OHNE Flask/COM.

Zweck
-----
Läuft PARALLEL zum operativen Zeitmess-Pfad in ``ring_server.py`` und verändert
diesen in keiner Weise. Zeichnet jede vom TIMY empfangene Zeile auf, paart
Start/Stop/RT über die LAUF-NUMMER (das TIMY kann mehrere Zeiten gleichzeitig
laufen lassen) und vergleicht die selbst berechnete Zeit gegen die RT-Zeile
(= Wert auf der Anzeigetafel). Datengrundlage für die spätere Fehler-Analyse am
Wochenende (Weg B, 1 Ring, EXE): ``delta_vs_timy`` sollte durchgehend 0.00 sein.

Diese Logik ist bewusst aus dem Standalone-Recorder (tools/timy_recorder)
übernommen, der gegen echte Aufnahmen verifiziert wurde — inkl. des dort
gefundenen Pairing-Fixes (Paarung über die Lauf-Nummer statt Ein-Slot-Logik).

Das Modul hat KEINE Abhängigkeit zu Flask/SocketIO/COM und ist damit in
``tests_pure`` ohne Hardware testbar.

Erkannte TIMY-Zeilenformate (aus echten Aufnahmen)
--------------------------------------------------
  '0006 C0  13:20:16.0431 00'   Start   (Kanal C0 oder C0M)
  '0006 C1  13:20:21.0159 00'   Stop    (Kanal C1 oder C1M)
  '0006 RT  00:00:04.97   00'   Laufzeit laut TIMY (= Anzeigetafel; RT/RTM)
  '?0001 C1M 13:17:01.71  00'   vom TIMY nachträglich korrigierter Impuls ('?')
  'TIMY: 480170000'             laufende Uhr (Rauschen, wird ignoriert)

CSV-Spalten (eine Zeile pro Lauf):
  idx, run_no, start_tod, stop_tod, raw_diff_s, final_time_s,
  timy_rt_s, delta_vs_timy_s, start_interval_s, flags
"""
from __future__ import annotations

import math
import re

# Impuls- UND RT-Zeilen: optionales '?', Lauf-Nummer, Kanal, Zeit(HH:MM:SS.frac).
_LINE_RE = re.compile(r'^\s*(\?)?\s*(\d+)\s+([A-Za-z]\w*)\s+(\d{2}:\d{2}:\d{2}\.\d+)')
# Laufende Uhr des TIMY (Rauschen): 'TIMY: 480170000'
_HEARTBEAT_RE = re.compile(r'^\s*TIMY:\s*\d+\s*$')


def parse_timy_line(line: str):
    """Zerlegt eine TIMY-Zeile.

    Rückgabe dict | None:
      {'kind': 'start'|'stop'|'timy_rt'|'other',
       'channel', 'run_no', 'time_of_day', 'corrected': bool}
    """
    m = _LINE_RE.match(line or "")
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
    """HH:MM:SS.frac -> Sekunden. Funktioniert für Tageszeit UND für die
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
    Epsilon schützt gegen Float-Ungenauigkeit (z.B. 35.68*100 = 3567.9999...)."""
    return math.floor(diff_s * 100 + 1e-9) / 100


class DiagRecorder:
    """Verarbeitet rohe TIMY-Zeilen, paart über die Lauf-Nummer und meldet pro
    Lauf eine strukturierte Zeile (CSV) sowie menschenlesbare Analyse-Zeilen.

    Reine Logik: schreibt nichts selbst, sondern ruft zwei Callbacks:
      ``log_fn(text)``  — eine Analyse-/Hinweiszeile (ohne Zeitstempel).
      ``csv_fn(line)``  — eine fertige CSV-Zeile inkl. '\\n' (Header zuerst).
    Fehlt ein Callback, wird dieser Kanal einfach nicht bespielt. Beide
    Callbacks dürfen frei Exceptions werfen — ``handle_line`` fängt alles ab,
    damit der Diagnose-Pfad NIE den Ring-Server stört.

    Pairing über die Lauf-Nummer (run_no): offene Starts liegen in
    ``open_starts``; beim C1 wird der passende Start gesucht, das Ergebnis in
    ``pending_finish`` geparkt und erst mit der RT-Zeile (Vergleich
    berechnet<->TIMY) final als CSV-Zeile gemeldet. Ohne RT wird spätestens
    beim nächsten C0 derselben Nummer bzw. beim ``close()`` geflusht.
    """

    CSV_HEADER = ("idx,run_no,start_tod,stop_tod,raw_diff_s,final_time_s,"
                  "timy_rt_s,delta_vs_timy_s,start_interval_s,flags\n")

    def __init__(self, ring="ring", *, log_fn=None, csv_fn=None):
        self.ring = ring
        self._log_fn = log_fn
        self._csv_fn = csv_fn
        self._csv_header_sent = False

        # Zustand
        self.open_starts: dict = {}       # run_no -> {idx, start_tod, interval, flags}
        self.pending_finish: dict = {}    # run_no -> berechneter Lauf (wartet auf RT)
        self.prev_start_tod = None        # letzter C0 nach Zeit (für Intervall)
        self.idx = 0
        self.heartbeats = 0

    # -- interne Helfer ----------------------------------------------------
    def _log(self, text: str) -> None:
        if not self._log_fn:
            return
        try:
            self._log_fn(text)
        except Exception:
            pass  # Diagnose darf den Ring-Server nie stören

    def _emit_row(self, rec: dict) -> None:
        if not self._csv_fn:
            return

        def f(x):
            return "" if x is None else (f"{x:.4f}" if isinstance(x, float) else str(x))

        try:
            if not self._csv_header_sent:
                self._csv_fn(self.CSV_HEADER)
                self._csv_header_sent = True
            self._csv_fn(
                f"{f(rec.get('idx'))},{rec.get('run_no') or ''},"
                f"{rec.get('start_tod') or ''},{rec.get('stop_tod') or ''},"
                f"{f(rec.get('raw_diff'))},{f(rec.get('final_time'))},"
                f"{f(rec.get('timy_rt'))},{f(rec.get('delta'))},"
                f"{f(rec.get('interval'))},{rec.get('flags') or ''}\n"
            )
        except Exception:
            pass

    @staticmethod
    def _add_flag(rec: dict, flag: str) -> None:
        cur = rec.get('flags') or ''
        rec['flags'] = f"{cur}|{flag}" if cur else flag

    # -- Haupteinstieg: eine rohe TIMY-Zeile ------------------------------
    def handle_line(self, line: str):
        """Verarbeitet eine rohe TIMY-Zeile. Gibt den gemeldeten Record (dict)
        zurück, wenn dieser Aufruf eine CSV-Zeile erzeugt hat, sonst None.
        Wirft NIE — alle internen Fehler werden geschluckt."""
        try:
            return self._handle_line(line)
        except Exception:
            return None

    def _handle_line(self, line: str):
        line = (line or "").strip()
        if not line:
            return None
        if _HEARTBEAT_RE.match(line):
            self.heartbeats += 1              # laufende Uhr: nur zählen
            return None
        parsed = parse_timy_line(line)
        if not parsed:
            self._log(f"raw={line!r} | MARKER/UNMATCHED")
            return None

        corr = " [KORREKTUR '?']" if parsed['corrected'] else ""
        self._log(f"raw={line!r} | run={parsed['run_no']} ch={parsed['channel']} "
                  f"kind={parsed['kind']} tod={parsed['time_of_day']}{corr}")

        if parsed['kind'] == 'start':
            self._on_start(parsed)
        elif parsed['kind'] == 'stop':
            self._on_stop(parsed)
        elif parsed['kind'] == 'timy_rt':
            return self._on_timy_rt(parsed)
        return None

    def _on_start(self, p: dict) -> None:
        run_no, tod = p['run_no'], p['time_of_day']
        self.idx += 1
        interval = None
        if self.prev_start_tod:
            delta = time_str_to_seconds(tod) - time_str_to_seconds(self.prev_start_tod)
            if delta > 0:                     # negativ = Mitternacht/Fehlimpuls
                interval = delta
        if run_no in self.open_starts:
            self._log(f"  >> HINWEIS: Lauf {run_no} hatte bereits einen offenen Start — überschrieben.")
        self.open_starts[run_no] = {
            "idx": self.idx, "start_tod": tod, "interval": interval,
            "flags": "corrected" if p['corrected'] else "",
        }
        self.prev_start_tod = tod
        iv = f"{interval:.3f}s seit letztem Start" if interval is not None else "erster Start"
        self._log(f"  >> START #{self.idx} Lauf {run_no} tod={tod}  ({iv})")

    def _on_stop(self, p: dict) -> None:
        run_no, tod = p['run_no'], p['time_of_day']
        start = self.open_starts.pop(run_no, None)
        if start is None:
            self._log(f"  >> HINWEIS: C1 Lauf {run_no} ({tod}) ohne passenden offenen Start — als no_start vermerkt.")
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
            self._log(f"  >> FEHLER: ungültige Zeit (start_s={start_s} stop_s={stop_s}).")
            rec.update(raw_diff=None, final_time=None)
            self._add_flag(rec, "invalid")
        else:
            final_time = floor_hundredths(raw_diff)
            rec.update(raw_diff=raw_diff, final_time=final_time)
            self._log(
                f"  >> BERECHNUNG: Lauf {run_no} start={start['start_tod']!r} stop={tod!r} "
                f"raw_diff={raw_diff!r} -> final_time={final_time!r} (warte auf RT-Vergleich)"
            )
        self.pending_finish[run_no] = rec

    def _on_timy_rt(self, p: dict):
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
        else:
            self._log(f"  >> RT Lauf {run_no}: TIMY={timy_rt:.2f} (keine eigene Berechnung vorhanden).")
        self._emit_row(rec)
        return rec

    def close(self) -> None:
        """Flusht übrig gebliebene Läufe (C1 ohne RT, Start ohne C1)."""
        for run_no, rec in list(self.pending_finish.items()):
            self._add_flag(rec, "no_rt")
            self._emit_row(rec)
            self.pending_finish.pop(run_no, None)
        for run_no, start in list(self.open_starts.items()):
            self._emit_row({
                "idx": start["idx"], "run_no": run_no, "start_tod": start["start_tod"],
                "stop_tod": None, "raw_diff": None, "final_time": None,
                "timy_rt": None, "delta": None, "interval": start["interval"],
                "flags": (start.get("flags") + "|no_c1").strip("|") if start.get("flags") else "no_c1",
            })
        self.open_starts.clear()
