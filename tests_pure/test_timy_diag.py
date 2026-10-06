"""Pure-Tests für den Diagnose-Recorder des Ring-Servers (web_app/ring_server/timy_diag.py).

Prüft die drei Kerneigenschaften, die am Wochenende tragen:
  1. floor-auf-0.01-Rechnung stimmt mit der RT-Zeile überein (delta == 0),
  2. Pairing über die Lauf-Nummer bei ÜBERLAPPENDEN Starts (der Bug, den der
     Standalone-Recorder im Ein-Slot-Modus hatte),
  3. robuste Randfälle (RT ohne C1, Start ohne C1, Intervall, kaputte Zeile).
"""
from web_app.ring_server.timy_diag import DiagRecorder, floor_hundredths, parse_timy_line


def _make():
    rows, logs = [], []
    rec = DiagRecorder(ring="Ring 1", log_fn=logs.append, csv_fn=rows.append)
    return rec, rows, logs


def _data_rows(rows):
    """CSV-Zeilen ohne Header, als Liste von Spaltenlisten."""
    return [r.strip().split(",") for r in rows if not r.startswith("idx,")]


def test_delta_zero_for_floor_formula():
    rec, rows, _ = _make()
    rec.handle_line("0006 C0  13:20:16.0431 00")
    rec.handle_line("0006 C1  13:20:21.0159 00")
    # raw_diff = 4.9728 -> floor auf 0.01 = 4.97; RT der Anzeigetafel = 4.97
    out = rec.handle_line("0006 RT  00:00:04.97   00")
    assert out["final_time"] == 4.97
    assert out["timy_rt"] == 4.97
    assert out["delta"] == 0.0
    data = _data_rows(rows)
    assert len(data) == 1
    assert data[0][5] == "4.9700"       # final_time_s
    assert data[0][7] == "0.0000"       # delta_vs_timy_s


def test_pairing_with_overlapping_starts():
    """Zwei Hunde gleichzeitig unterwegs: der zweite startet, bevor der erste
    im Ziel ist. Die Zuordnung MUSS über die Lauf-Nummer laufen."""
    rec, rows, _ = _make()
    rec.handle_line("0001 C0  10:00:00.0000 00")   # Hund 1 Start
    rec.handle_line("0002 C0  10:00:05.0000 00")   # Hund 2 Start (überlappt)
    rec.handle_line("0001 C1  10:00:30.0000 00")   # Hund 1 Ziel -> 30.00
    rec.handle_line("0001 RT  00:00:30.00   00")
    rec.handle_line("0002 C1  10:00:40.0000 00")   # Hund 2 Ziel -> 35.00
    rec.handle_line("0002 RT  00:00:35.00   00")
    data = {r[1]: r for r in _data_rows(rows)}
    assert data["0001"][5] == "30.0000"
    assert data["0002"][5] == "35.0000"
    assert data["0001"][7] == "0.0000" and data["0002"][7] == "0.0000"


def test_start_interval_measured():
    rec, rows, _ = _make()
    rec.handle_line("0001 C0  10:00:00.0000 00")
    rec.handle_line("0002 C0  10:00:18.5000 00")   # 18.5s nach dem ersten Start
    rec.close()
    data = {r[1]: r for r in _data_rows(rows)}
    assert data["0001"][8] == ""                    # erster Start: kein Intervall
    assert data["0002"][8] == "18.5000"
    # Beide ohne C1 -> no_c1 geflusht
    assert "no_c1" in data["0001"][9] and "no_c1" in data["0002"][9]


def test_rt_only_without_c1():
    rec, rows, _ = _make()
    out = rec.handle_line("0007 RT  00:00:12.34   00")
    assert out["timy_rt"] == 12.34
    assert out["final_time"] is None
    assert _data_rows(rows)[0][9] == "rt_only"


def test_corrected_impulse_flagged():
    rec, rows, _ = _make()
    rec.handle_line("0003 C0  09:00:00.0000 00")
    rec.handle_line("?0003 C1M 09:00:10.0000 00")   # nachträglich korrigiert
    rec.handle_line("0003 RT  00:00:10.00   00")
    assert "corrected" in _data_rows(rows)[0][9]


def test_heartbeat_and_garbage_are_safe():
    rec, rows, logs = _make()
    assert rec.handle_line("TIMY: 480170000") is None
    assert rec.handle_line("") is None
    assert rec.handle_line("völliger Unsinn ohne Zeit") is None
    assert rec.heartbeats == 1
    assert rows == []                               # keine Datenzeile erzeugt


def test_floor_and_parse_helpers():
    assert floor_hundredths(4.9728) == 4.97
    assert floor_hundredths(35.68) == 35.68         # Epsilon gegen 3567.999...
    p = parse_timy_line("0006 C0  13:20:16.0431 00")
    assert p["kind"] == "start" and p["run_no"] == "0006"
    assert parse_timy_line("TIMY: 1") is None
