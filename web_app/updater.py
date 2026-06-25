"""Einfacher Update-Check gegen GitHub Releases.

Beim Start ruft die EXE :func:`check_and_print` auf. Bei verfügbarem Update
wird ein Hinweis in der Konsole ausgegeben. Bewusst kein Auto-Download:

  - Der laufende Prozess ist gelockt; ein In-Place-Update wäre eine eigene
    Helper-EXE wert. Das übersteigt den jetzigen Bedarf.
  - Der User soll bewusst aktualisieren (vor allem am Veranstaltungstag).

Bei Netzfehler / Offline wird *nichts* ausgegeben - der Start darf nie an
einem fehlenden Update-Check scheitern.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error
from typing import Optional

# GitHub-Repo (Public Releases). Override via Env AGILITY_UPDATE_REPO.
_DEFAULT_REPO = "christiani93/AgilitySoftware"


def _repo() -> str:
    return os.environ.get("AGILITY_UPDATE_REPO") or _DEFAULT_REPO


def _api_url() -> str:
    return f"https://api.github.com/repos/{_repo()}/releases/latest"


def _parse_version(s: str) -> tuple:
    """'v4.5' -> (4, 5);  '4.5.1' -> (4, 5, 1);  'foo' -> ('foo',)."""
    if not s:
        return ()
    s = s.strip().lstrip("vV")
    parts = s.split(".")
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except ValueError:
            out.append(p)
    return tuple(out)


def check_for_update(current_version: str, timeout: float = 3.0) -> Optional[dict]:
    """Fragt GitHub nach dem letzten Release.

    Returns:
        ``None`` bei Netzfehler/Offline/Repo unbekannt.
        Sonst ``{available: bool, latest: str, html_url: str, assets: [...]}``.
    """
    req = urllib.request.Request(
        _api_url(),
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "AgilitySoftware-Updater"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            ConnectionError, json.JSONDecodeError, OSError):
        return None

    latest = (data.get("tag_name") or "").strip()
    if not latest:
        return None

    assets = []
    for a in data.get("assets") or []:
        assets.append({
            "name": a.get("name"),
            "url": a.get("browser_download_url"),
            "size": a.get("size"),
        })

    return {
        "available": _parse_version(latest) > _parse_version(current_version),
        "latest": latest,
        "html_url": data.get("html_url"),
        "assets": assets,
        "current": current_version,
    }


def print_update_banner(info: dict, component: str = "AgilitySoftware") -> None:
    """Hübsche Konsolen-Ausgabe. Nur drucken wenn Update verfügbar."""
    if not info or not info.get("available"):
        return
    print("")
    print("------------------------------------------------------------")
    print(f"  >> UPDATE verfügbar für {component}")
    print(f"     Installiert: {info.get('current')}   Neu: {info.get('latest')}")
    if info.get("html_url"):
        print(f"     Release:     {info['html_url']}")
    # Passenden Asset hervorheben falls vorhanden
    needle = component.lower()
    for a in info.get("assets", []):
        if needle in (a.get("name") or "").lower():
            print(f"     Download:    {a.get('url')}")
            break
    print("------------------------------------------------------------")
    print("")


def check_and_print(current_version: str, component: str = "AgilitySoftware",
                    timeout: float = 3.0) -> None:
    """Convenience: prüft und gibt ggf. Banner aus. Niemals exception."""
    if os.environ.get("AGILITY_NO_UPDATE_CHECK"):
        return
    try:
        info = check_for_update(current_version, timeout=timeout)
        print_update_banner(info, component=component)
    except Exception:
        pass
