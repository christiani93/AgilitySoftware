# utils.py
import os
import json
import csv
from io import StringIO
from datetime import datetime, timedelta
import math
import uuid
from flask import flash
import random

CATEGORY_SORT_ORDER = {'Large': 0, 'Intermediate': 1, 'Medium': 2, 'Small': 3}

def get_category_sort_key(category_name):
    return CATEGORY_SORT_ORDER.get(category_name, 99)


def _to_float(value, default=0.0):
    """
    Robuste Float-Konvertierung:
    - erlaubt None und '' (-> default)
    - ersetzt Komma durch Punkt
    - fängt ValueError/TypeError ab
    """
    try:
        if value is None:
            return default
        if isinstance(value, str):
            v = value.strip()
            if not v:
                return default
            v = v.replace(',', '.')
            return float(v)
        return float(value)
    except (ValueError, TypeError):
        return default

def _load_data(filename, default_data=[]):
    filepath = os.path.join('data', filename)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default_data

def _save_data(filename, data):
    filepath = os.path.join('data', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def _load_settings():
    defaults = {
        "ranking_points": [10, 8, 6, 4, 2],
        "time_per_starter": 90,
        "sct_factors": { "Agility": {"1": 2.5, "2": 3.0, "3": 3.5}, "Jumping": {"1": 3.0, "2": 3.5, "3": 4.0} },
        "start_number_schema_template": {
            "Large-3": 1300, "Large-2": 1200, "Large-1": 1100, "Large-Oldie": 1400,
            "Intermediate-3": 2300, "Intermediate-2": 2200, "Intermediate-1": 2100, "Intermediate-Oldie": 2400,
            "Medium-3": 3300, "Medium-2": 3200, "Medium-1": 3100, "Medium-Oldie": 3400,
            "Small-3": 4300, "Small-2": 4200, "Small-1": 4100, "Small-Oldie": 4400
        }
    }
    settings = _load_data('settings.json', defaults)
    for key, value in defaults.items():
        settings.setdefault(key, value)
    return settings

def _get_active_event_id():
    active_event_data = _load_data('active_event.json', {})
    return active_event_data.get('active_event_id')

def _get_active_event():
    active_id = _get_active_event_id()
    if not active_id: return None
    events = _load_data('events.json')
    return next((e for e in events if e.get('id') == active_id), None)

def _decode_csv_file(file_storage):
    try: return file_storage.read().decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            file_storage.stream.seek(0)
            return file_storage.stream.read().decode('iso-8859-1')
        except Exception as e:
            flash(f"Konnte die Datei nicht dekodieren: {e}", "error")
            return None
            
def _import_csv_data(file_storage, data_filename, id_field):
    content = _decode_csv_file(file_storage)
    if not content: return 0, 0
    all_data, existing_ids = _load_data(data_filename), {str(item.get(id_field)) for item in _load_data(data_filename)}
    reader, added_count, skipped_count = csv.DictReader(StringIO(content), delimiter=';'), 0, 0
    for row in reader:
        row_keys_lower, id_field_lower = {k.lower().strip(): k for k in row.keys()}, id_field.lower().strip()
        csv_id_val = None
        if id_field_lower in row_keys_lower:
            csv_id_val = row[row_keys_lower[id_field_lower]].strip()
        if not csv_id_val or csv_id_val in existing_ids:
            skipped_count += 1
            continue
        new_item = {key.strip(): val.strip() for key, val in row.items() if val}
        if id_field not in new_item: new_item[id_field] = csv_id_val
        if id_field == 'id' and not new_item.get('id'): new_item['id'] = str(uuid.uuid4())
        all_data.append(new_item)
        existing_ids.add(csv_id_val)
        added_count += 1
    _save_data(data_filename, all_data)
    return added_count, skipped_count

def _get_concrete_run_list(event):
    ordered_runs, run_order, all_runs = [], event.get('run_order', []), event.get('runs', [])
    for run in all_runs:
        if 'id' not in run: run['id'] = str(uuid.uuid4())
    run_map = {r['id']: r for r in all_runs}
    for block in run_order:
        if block.get('laufart') in ['Pause', 'Umbau', 'Briefing', 'Vorbereitung', 'Grossring']:
            ordered_runs.append(block)
            continue
        
        block_runs_ids = [r['id'] for r in all_runs if r.get('laufart') == block.get('laufart') and (block.get('kategorie') == 'Alle' or r.get('kategorie') == block.get('kategorie')) and (block.get('klasse') == 'Alle' or str(r.get('klasse')) == str(block.get('klasse')))]
        block_runs = [run_map[rid] for rid in block_runs_ids if rid in run_map]
        
        kat_sort = block.get('kat_sort')
        kl_sort = block.get('kl_sort')

        if kat_sort:
             block_runs.sort(key=lambda r: get_category_sort_key(r.get('kategorie', '')), reverse=(kat_sort == 'desc'))
        if kl_sort:
            class_order = {str(i): i for i in range(1, 4)}; class_order['Oldie'] = 4
            block_runs.sort(key=lambda r: (class_order.get(str(r.get('klasse')), 99)), reverse=(kl_sort == 'desc'))
            
        ordered_runs.extend(block_runs)
    return ordered_runs

def _place_entries_with_distance(entries, distance):
    start_at_end_entries = [e for e in entries if e.get('start_at_end') or e.get('start_last')]
    regular_entries = [e for e in entries if not e.get('start_at_end')]
    
    final_order, handler_last_pos, deferred_entries = [], {}, []
    all_to_place = list(regular_entries)
    while all_to_place:
        entry = all_to_place.pop(0)
        handler = (entry.get('handler_id') or entry.get('Hundefuehrer_ID') or entry.get('HF_ID') or entry.get('Hundefuehrer'))
        last_pos = handler_last_pos.get(handler)
        if last_pos is None or len(final_order) - last_pos >= distance:
            final_order.append(entry)
            handler_last_pos[handler] = len(final_order) - 1
            if deferred_entries:
                all_to_place = deferred_entries + all_to_place
                deferred_entries = []
        else: deferred_entries.append(entry)
    final_order.extend(deferred_entries)
    final_order.extend(start_at_end_entries)
    return final_order

def _calculate_run_results(run, settings):
    results = []
    laufdaten = run.get('laufdaten', {}) or {}
    run['laufdaten'] = laufdaten
    klasse = str(run.get('klasse'))
    laufart = run.get('laufart')
    parcours_laenge = _to_float(laufdaten.get('parcours_laenge'), 0.0)
    sct_factor_config = {
        '2': {'standard': 1.4, 'qualification': 1.2},
        '3': {'standard': 1.3, 'qualification': 1.15},
    }
    is_qualification = bool(
        laufdaten.get('is_qualification')
        or laufdaten.get('qualification_mode')
        or laufdaten.get('sct_mode') == 'qualification'
    )
    auto_dis_on_mct_exceeded = laufdaten.get('auto_dis_on_mct_exceeded', True)

    sct_seconds, mct_seconds = None, None
    sct_for_timefaults = None

    if klasse in ['1', 'Oldie']:
        manual_sct = _to_float(laufdaten.get('standardzeit_sct'), None)
        manual_sct = manual_sct if manual_sct is not None else _to_float(laufdaten.get('standardzeit_sct_manuell'), None)
        if manual_sct is not None:
            sct_seconds = manual_sct
        elif parcours_laenge > 0:
            geschwindigkeit = _to_float(laufdaten.get('geschwindigkeit'), None)
            if geschwindigkeit:
                sct_seconds = parcours_laenge / geschwindigkeit
        if sct_seconds is not None:
            mct_seconds = sct_seconds * 1.5
    elif klasse in ['2', '3']:
        if parcours_laenge > 0:
            if laufart == 'Agility':
                mct_seconds = parcours_laenge / 2.5
            elif laufart == 'Jumping':
                mct_seconds = parcours_laenge / 3.0
            else:
                mct_seconds = parcours_laenge / 2.5

        # Bestplatziertes Team bestimmen (wenigste Fehler+Verweigerungen, dann schnellste Nettozeit)
        best_candidate = None
        for entry in run.get('entries', []):
            result_data = entry.get('result') or {}
            dis_abr = result_data.get('disqualifikation')
            if dis_abr in ["DIS", "ABR", "DNS"]:
                continue
            laufzeit = _to_float(result_data.get('zeit'), None)
            if laufzeit is None:
                continue
            if auto_dis_on_mct_exceeded and mct_seconds is not None and math.ceil(laufzeit) > math.ceil(mct_seconds):
                continue
            fehler = _to_int(result_data.get('fehler', '0'), 0)
            verweigerungen = _to_int(result_data.get('verweigerungen', '0'), 0)
            faults_total = fehler + verweigerungen
            candidate = (faults_total, laufzeit)
            if best_candidate is None or candidate < best_candidate:
                best_candidate = candidate

        if best_candidate:
            base_time = best_candidate[1]
            factor_cfg = sct_factor_config.get(klasse, {'standard': 1.0, 'qualification': 1.0})
            factor = factor_cfg['qualification'] if is_qualification else factor_cfg['standard']
            sct_seconds = base_time * factor

        if sct_seconds is None:
            fallback_sct = _to_float(laufdaten.get('standardzeit_sct'), None)
            sct_seconds = fallback_sct if fallback_sct is not None else sct_seconds

    if sct_seconds is not None:
        sct_for_timefaults = math.ceil(sct_seconds)
        laufdaten['standardzeit_sct_berechnet'] = round(sct_seconds, 2)
        laufdaten['standardzeit_sct_gerundet'] = sct_for_timefaults
    else:
        laufdaten['standardzeit_sct_berechnet'] = None
        laufdaten['standardzeit_sct_gerundet'] = None

    if mct_seconds is not None:
        laufdaten['maximalzeit_mct_berechnet'] = round(mct_seconds, 2)
        laufdaten['maximalzeit_mct_gerundet'] = math.ceil(mct_seconds)
    else:
        laufdaten['maximalzeit_mct_berechnet'] = None
        laufdaten['maximalzeit_mct_gerundet'] = None

    for entry in run.get('entries', []):
        res = entry.copy()
        result_data = res.get('result')

        if result_data:
            dis_abr = result_data.get('disqualifikation')
            laufzeit_str = result_data.get('zeit')
            fehler_str = result_data.get('fehler', '0') or '0'
            verweigerungen_str = result_data.get('verweigerungen', '0') or '0'
            
            fehler = _to_int(fehler_str, 0)
            verweigerungen = _to_int(verweigerungen_str, 0)

            laufzeit = _to_float(laufzeit_str, None)

            auto_dis_mct = (
                auto_dis_on_mct_exceeded
                and laufzeit is not None
                and mct_seconds is not None
                and math.ceil(laufzeit) > math.ceil(mct_seconds)
            )

            if dis_abr in ["DIS", "ABR", "DNS"] or auto_dis_mct:
                dis_value = dis_abr if dis_abr in ["DIS", "ABR", "DNS"] else "DIS"
                res.update({
                    'fehler_total': 999,
                    'zeit_total': 999.99,
                    'qualifikation': dis_value,
                    'fehler_parcours_anzahl': fehler,
                    'verweigerung_parcours_anzahl': verweigerungen,
                    'fehler_parcours': fehler,
                    'verweigerung_parcours': verweigerungen,
                    'disqualifikation': dis_value,
                })
            elif laufzeit is not None:
                fehler_parcours = fehler * 5 + verweigerungen * 5
                if sct_for_timefaults is None:
                    fehler_zeit = 0
                else:
                    fehler_zeit = max(0, laufzeit - sct_for_timefaults)
                fehler_total = fehler_parcours + fehler_zeit
                qualifikation = 'N/A'
                if fehler_total < 6:
                    qualifikation = "V0" if fehler_total == 0 else "V"
                elif fehler_total < 16:
                    qualifikation = "SG"
                elif fehler_total < 26:
                    qualifikation = "G"
                else:
                    qualifikation = "NB"
                res.update({
                    'fehler_zeit': fehler_zeit,
                    'fehler_total': fehler_total,
                    'zeit_total': laufzeit,
                    'fehler_parcours': fehler_parcours,
                    'verweigerung_parcours': verweigerungen,
                    'fehler_parcours_anzahl': fehler,
                    'verweigerung_parcours_anzahl': verweigerungen,
                    'qualifikation': qualifikation,
                    'disqualifikation': result_data.get('disqualifikation'),
                })
            else:
                res.update({'fehler_total': 998, 'zeit_total': 998.99, 'qualifikation': 'N/A', 'disqualifikation': result_data.get('disqualifikation')})
        else:
            res.update({'fehler_total': 998, 'zeit_total': 998.99, 'qualifikation': 'N/A'})
        
        results.append(res)
        
    results.sort(key=lambda x: (x.get('fehler_total', 999), x.get('zeit_total', 999)))
    rank = 1
    for res in results:
        if res.get('fehler_total', 999) < 998:
            res['platz'] = rank
            rank += 1
    return results

def _calculate_timelines(event, round_to_minutes=None):
    settings = _load_settings()
    time_per_starter = settings.get('time_per_starter', 90)
    start_times_by_ring, current_times = event.get('start_times_by_ring', {}), {}
    num_rings = event.get('num_rings', 1)
    for ring_num in range(1, num_rings + 1):
        ring_key, start_time_str = f"ring_{ring_num}", start_times_by_ring.get(f"ring_{ring_num}", '07:30')
        try: current_times[str(ring_num)] = datetime.strptime(f"{event.get('Datum')} {start_time_str}", '%Y-%m-%d %H:%M')
        except (ValueError, TypeError): current_times[str(ring_num)] = datetime.now().replace(hour=7, minute=30, second=0, microsecond=0)
    timelines_by_ring = {str(i): [] for i in range(1, num_rings + 1)}
    for block in event.get('run_order', []):
        duration_minutes, num_starters = 0, 0
        is_grossring = block.get('is_grossring', False)
        if block.get('laufart') in ['Pause', 'Umbau', 'Briefing', 'Vorbereitung', 'Grossring']:
            duration_minutes = int(block.get('duration', 15))
        else:
            runs_in_block = [r for r in event.get('runs', []) if r.get('laufart') == block.get('laufart') and (block.get('kategorie') == 'Alle' or r.get('kategorie') == block.get('kategorie')) and (block.get('klasse') == 'Alle' or str(r.get('klasse')) == str(block.get('klasse')))]
            num_starters = sum(len(r.get('entries', [])) for r in runs_in_block)
            duration_minutes = (num_starters * time_per_starter) / 60
        block_duration = timedelta(minutes=duration_minutes)
        def get_times(start_dt, duration):
            end_dt = start_dt + duration
            if round_to_minutes:
                def _round_time(dt, n):
                    discard = timedelta(minutes=dt.minute % n, seconds=dt.second, microseconds=dt.microsecond)
                    dt -= discard
                    if discard >= timedelta(minutes=n/2):
                        dt += timedelta(minutes=n)
                    return dt
                return _round_time(start_dt, round_to_minutes), _round_time(end_dt, round_to_minutes)
            return start_dt, end_dt
        if is_grossring:
            start_time_dt = max(current_times.get('1', datetime.min), current_times.get('2', datetime.min))
            start_time, end_time = get_times(start_time_dt, block_duration)
            timeline_item = {'block': block, 'start_time': start_time.strftime('%H:%M'), 'end_time': end_time.strftime('%H:%M'), 'duration': duration_minutes, 'num_starters': num_starters}
            if '1' in timelines_by_ring: timelines_by_ring['1'].append(timeline_item)
            if '2' in timelines_by_ring: timelines_by_ring['2'].append(timeline_item)
            current_times['1'] = end_time; current_times['2'] = end_time
        else:
            ring = str(block.get('ring'))
            if ring not in current_times: continue
            start_time_dt = current_times[ring]
            start_time, end_time = get_times(start_time_dt, block_duration)
            timeline_item = {'block': block, 'start_time': start_time.strftime('%H:%M'), 'end_time': end_time.strftime('%H:%M'), 'duration': duration_minutes, 'num_starters': num_starters}
            timelines_by_ring[ring].append(timeline_item)
            current_times[ring] = end_time
    return timelines_by_ring


def _to_int(x, default=0):
    if isinstance(x, bool):
        return default
    if isinstance(x, int):
        return x
    try:
        s = ("" if x is None else str(x)).strip().replace(",", ".")
        if s == "" or s.lower() in ("nan","none","null","-"):
            return default
        f = float(s)
        return int(round(f))
    except Exception:
        try:
            return int(x)
        except Exception:
            return default


def judge_name(judges, judge_id):
    """Gibt 'Vorname Nachname' zum judge_id zurück oder 'Unbekannt'."""
    try:
        jid = str(judge_id)
        for j in judges or []:
            if str(j.get('id')) == jid:
                first = (j.get('firstname') or j.get('vorname') or '').strip()
                last  = (j.get('lastname')  or j.get('nachname') or '').strip()
                name = (first + ' ' + last).strip()
                return name or 'Unbekannt'
    except Exception:
        pass
    return 'Unbekannt'


def _apply_sct_mct_factors(laufdaten: dict, settings: dict):
    '''
    Berechnet SCT/MCT-Faktoren für Klassen 2 und 3 anhand settings['sct_factors'].
    '''
    try:
        la = (laufdaten.get('laufart') or '').strip()
        kl = str(laufdaten.get('klasse') or '').strip()
        facs = (settings or {}).get('sct_factors', {}).get(la, {})
        fac = float(facs.get(kl, 1.0))
        if laufdaten.get('sct_direkt'):
            base_sct = float(str(laufdaten.get('standardzeit_sct')).replace(',', '.'))
        else:
            gl = float(str(laufdaten.get('parcours_laenge')).replace(',', '.'))
            v  = float(str(laufdaten.get('geschwindigkeit')).replace(',', '.'))
            base_sct = gl / v if v > 0 else 0.0
        sct = base_sct * fac
        laufdaten['standardzeit_sct_gerundet'] = round(sct, 2)
        laufdaten['maximalzeit_mct_gerundet'] = round(sct * 1.5, 2)
    except Exception:
        laufdaten['standardzeit_sct_gerundet'] = laufdaten.get('standardzeit_sct_gerundet', 999)
        laufdaten['maximalzeit_mct_gerundet']  = laufdaten.get('maximalzeit_mct_gerundet', 999)
