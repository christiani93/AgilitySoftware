"""
SWG-R-10: Ausländische Lizenzen müssen einen gültigen IOC-Ländercode tragen.
Die Export-Route prüft das vorab und listet ungültige Codes (häufige Falle:
Deutschland ist IOC 'GER', nicht ISO 'DEU').
"""
from ioc_codes import is_valid_ioc_code, extract_country_code
from blueprints.routes_print import _invalid_ioc_licenses, _tkamo_run_status


def test_valid_ioc_codes():
    assert is_valid_ioc_code("GER")
    assert is_valid_ioc_code("FRA")
    assert is_valid_ioc_code("SUI")
    assert is_valid_ioc_code("ger")  # case-insensitiv


def test_invalid_ioc_codes():
    assert not is_valid_ioc_code("DEU")   # ISO, nicht IOC
    assert not is_valid_ioc_code("")
    assert not is_valid_ioc_code("XX")
    assert not is_valid_ioc_code("ABCD")


def test_extract_country_code():
    assert extract_country_code("FRA-105002") == "FRA"
    assert extract_country_code("GER12345") == "GER"
    assert extract_country_code("DEU-1") == "DEU"
    assert extract_country_code("12345") == ""      # CH, rein numerisch
    assert extract_country_code("") == ""


def _run(entries, klasse="1"):
    return {
        "laufart": "Agility", "kategorie": "Large", "klasse": klasse,
        "laufdaten": {"standardzeit_sct": 40, "parcours_laenge": 100},
        "entries": entries,
    }


def _entry(lic, zeit=38):
    return {"Lizenznummer": lic, "Hundename": "Rex", "Hundefuehrer": "Max Muster",
            "result": {"zeit": zeit, "fehler": 0, "verweigerungen": 0}}


def test_invalid_ioc_collected_from_complete_run():
    runs = [_run([_entry("DEU-123"), _entry("12345"), _entry("GER-9")])]
    statuses = [_tkamo_run_status(r, {}) for r in runs]
    invalid = _invalid_ioc_licenses(runs, statuses, {})
    codes = {i["code"] for i in invalid}
    assert codes == {"DEU"}  # nur die ISO-Variante, GER + CH sind ok


def test_no_invalid_when_all_valid():
    runs = [_run([_entry("FRA-1"), _entry("ITA-2"), _entry("99")])]
    statuses = [_tkamo_run_status(r, {}) for r in runs]
    assert _invalid_ioc_licenses(runs, statuses, {}) == []


def test_incomplete_run_not_checked():
    # Unvollständige Läufe werden gar nicht exportiert → auch nicht IOC-geprüft.
    runs = [_run([_entry("DEU-1"), {"Lizenznummer": "55"}])]  # 55 ohne Resultat → incomplete
    statuses = [_tkamo_run_status(r, {}) for r in runs]
    assert statuses[0][0] == "incomplete"
    assert _invalid_ioc_licenses(runs, statuses, {}) == []
