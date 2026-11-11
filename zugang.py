"""Zugänge und Rollen für das Unternehmer-Cockpit.

Rollen
- berater:  sieht alles (intern und extern, alle Mandanten, Mandanten-Übersicht, Datenquelle)
- inhaber:  sieht nur die eigene Firma (interner Modus), darf Datenquelle und Schwellen ändern
- mandant:  sieht nur seinen Mandanten (eine Region), andere Mandanten nur anonym im Benchmark

Die Zugänge stehen in zugaenge.json neben der App. Passwörter werden nie im Klartext gespeichert,
sondern als PBKDF2-SHA256-Hash mit eigenem Salz je Nutzer.

Befehle (im Ordner 11_cockpit_app):
    python zugang.py demo                         Demo-Zugänge für das Portfolio anlegen
    python zugang.py anlegen <name> berater       Zugang anlegen, Passwort wird abgefragt
    python zugang.py anlegen <name> inhaber
    python zugang.py anlegen <name> mandant <Region>
    python zugang.py liste                        vorhandene Zugänge zeigen
    python zugang.py loeschen <name>
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

DATEI = Path(os.environ.get("COCKPIT_ZUGAENGE", Path(__file__).resolve().parent / "zugaenge.json"))
ROLLEN = ("berater", "inhaber", "mandant")
REGIONEN = ("Central", "East", "South", "West")
RUNDEN = 200_000

# Demo-Zugänge: nur für die fiktiven Übungsdaten gedacht, die Passwörter stehen offen auf der Anmeldeseite
DEMO = {
    "berater": ("berater", None, "demo-berater"),
    "inhaber": ("inhaber", None, "demo-inhaber"),
    "central": ("mandant", "Central", "demo-central"),
    "east": ("mandant", "East", "demo-east"),
    "south": ("mandant", "South", "demo-south"),
    "west": ("mandant", "West", "demo-west"),
}


def _hash(passwort: str, salz: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", passwort.encode("utf-8"), bytes.fromhex(salz), RUNDEN).hex()


def laden() -> dict:
    """{"demo": bool, "nutzer": {name: {rolle, mandant, salz, hash}}}; leer, wenn keine Datei da ist."""
    try:
        return json.loads(DATEI.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"demo": False, "nutzer": {}}


def speichern(z: dict) -> None:
    DATEI.write_text(json.dumps(z, indent=2, ensure_ascii=False), encoding="utf-8")


def anlegen(z: dict, name: str, rolle: str, passwort: str, mandant: str | None = None) -> dict:
    name = name.strip().lower()
    if rolle not in ROLLEN:
        raise ValueError(f"Rolle muss eine von {', '.join(ROLLEN)} sein.")
    if rolle == "mandant" and mandant not in REGIONEN:
        raise ValueError(f"Mandant muss eine von {', '.join(REGIONEN)} sein.")
    if len(passwort) < 8:
        raise ValueError("Passwort braucht mindestens 8 Zeichen.")
    salz = secrets.token_hex(16)
    z["nutzer"][name] = {"rolle": rolle, "mandant": mandant if rolle == "mandant" else None,
                         "salz": salz, "hash": _hash(passwort, salz)}
    return z


def pruefen(z: dict, name: str, passwort: str) -> dict | None:
    """Gibt den Nutzer (ohne Hash) zurück, wenn Name und Passwort stimmen, sonst None."""
    n = z["nutzer"].get(name.strip().lower())
    if n is None:
        _hash(passwort, "00" * 16)          # gleiche Rechenzeit, verrät nicht, ob der Name existiert
        return None
    if not hmac.compare_digest(_hash(passwort, n["salz"]), n["hash"]):
        return None
    return {"name": name.strip().lower(), "rolle": n["rolle"], "mandant": n.get("mandant")}


def demo_anlegen() -> dict:
    z = {"demo": True, "nutzer": {}}
    for name, (rolle, mandant, pw) in DEMO.items():
        anlegen(z, name, rolle, pw, mandant)
    return z


if __name__ == "__main__":
    import getpass
    import sys

    arg = sys.argv[1:]
    if arg[:1] == ["demo"]:
        speichern(demo_anlegen())
        print(f"Demo-Zugänge geschrieben: {DATEI}")
    elif arg[:1] == ["anlegen"] and len(arg) >= 3:
        z = laden()
        pw = getpass.getpass("Passwort: ")
        if pw != getpass.getpass("Passwort wiederholen: "):
            sys.exit("Passwörter stimmen nicht überein.")
        z = anlegen(z, arg[1], arg[2], pw, arg[3] if len(arg) > 3 else None)
        z["demo"] = False          # eigene Zugänge: Demo-Hinweis auf der Anmeldeseite ausblenden
        speichern(z)
        print(f"Zugang '{arg[1]}' angelegt. Demo-Hinweis ausgeblendet; Demo-Zugänge ggf. mit 'loeschen' entfernen.")
    elif arg[:1] == ["liste"]:
        for name, n in laden()["nutzer"].items():
            print(f"{name:12} {n['rolle']:8} {n.get('mandant') or ''}")
    elif arg[:1] == ["loeschen"] and len(arg) == 2:
        z = laden()
        z["nutzer"].pop(arg[1].lower(), None)
        speichern(z)
        print(f"Zugang '{arg[1]}' gelöscht.")
    else:
        print(__doc__)
