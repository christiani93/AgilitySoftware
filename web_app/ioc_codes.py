"""
IOC-Ländercodes (NOC, dreistellig) für die Kennzeichnung ausländischer Lizenzen
in der TKAMO-Resultatmeldung (SWG-K-14 / SWG-R-10).

Quelle: offizielle IOC/NOC-Codeliste. Massgebend bleibt die geltende Liste des
IOC; diese Sammlung dient der Vorab-Prüfung beim Export.

WICHTIG: IOC-Codes weichen teils von ISO-3166-alpha-3 ab. Häufige Stolperfalle
bei Agility-Startern aus dem Nachbarland: Deutschland ist IOC **GER** (ISO wäre
DEU). Solche ISO-Codes werden von `is_valid_ioc_code` als ungültig gemeldet.
"""

# Aktuelle NOCs + gängige frühere Codes (um Fehlalarme zu vermeiden).
IOC_CODES = frozenset({
    # Europa
    "ALB", "AND", "ARM", "AUT", "AZE", "BLR", "BEL", "BIH", "BUL", "CRO",
    "CYP", "CZE", "DEN", "EST", "FIN", "FRA", "GEO", "GER", "GBR", "GRE",
    "HUN", "ISL", "IRL", "ISR", "ITA", "KOS", "LAT", "LIE", "LTU", "LUX",
    "MLT", "MDA", "MON", "MNE", "NED", "MKD", "NOR", "POL", "POR", "ROU",
    "RUS", "SMR", "SRB", "SVK", "SLO", "ESP", "SWE", "SUI", "TUR", "UKR",
    # Amerika
    "ARG", "ARU", "BAH", "BAR", "BIZ", "BOL", "BRA", "CAN", "CHI", "COL",
    "CRC", "CUB", "DMA", "DOM", "ECU", "ESA", "GRN", "GUA", "GUY", "HAI",
    "HON", "JAM", "MEX", "NCA", "PAN", "PAR", "PER", "PUR", "SKN", "LCA",
    "VIN", "SUR", "TTO", "URU", "USA", "VEN", "ISV", "ANT",
    # Afrika
    "ALG", "ANG", "BEN", "BOT", "BUR", "BDI", "CMR", "CPV", "CAF", "CHA",
    "COM", "CGO", "COD", "CIV", "DJI", "EGY", "GEQ", "ERI", "SWZ", "ETH",
    "GAB", "GAM", "GHA", "GUI", "GBS", "KEN", "LES", "LBR", "LBA", "MAD",
    "MAW", "MLI", "MTN", "MRI", "MAR", "MOZ", "NAM", "NIG", "NGR", "RWA",
    "STP", "SEN", "SEY", "SLE", "SOM", "RSA", "SSD", "SUD", "TAN", "TOG",
    "TUN", "UGA", "ZAM", "ZIM",
    # Asien
    "AFG", "BRN", "BAN", "BHU", "BRU", "CAM", "CHN", "TPE", "HKG", "IND",
    "INA", "IRI", "IRQ", "JPN", "JOR", "KAZ", "PRK", "KOR", "KUW", "KGZ",
    "LAO", "LBN", "MAS", "MDV", "MGL", "MYA", "NEP", "OMA", "PAK", "PLE",
    "PHI", "QAT", "KSA", "SGP", "SRI", "SYR", "TJK", "THA", "TLS", "TKM",
    "UAE", "UZB", "VIE", "YEM",
    # Ozeanien
    "ASA", "AUS", "COK", "FIJ", "GUM", "KIR", "MHL", "FSM", "NRU", "NZL",
    "PLW", "PNG", "SAM", "SOL", "TGA", "TUV", "VAN",
})


def is_valid_ioc_code(code: str) -> bool:
    """True, wenn `code` ein gültiger dreistelliger IOC-Ländercode ist."""
    return bool(code) and code.upper() in IOC_CODES


def extract_country_code(license_no: str) -> str:
    """Zieht den vorangestellten Ländercode aus einer ausländischen Lizenz.

    Intern gespeichert als "AAA-12345" (mit Trenner) oder bereits "AAA12345".
    Gibt die führenden Buchstaben zurück (leer, wenn keine).
    """
    if not license_no:
        return ""
    raw = str(license_no).strip()
    head = raw.split("-", 1)[0] if "-" in raw else raw
    letters = ""
    for ch in head:
        if ch.isalpha():
            letters += ch
        else:
            break
    return letters.upper()
