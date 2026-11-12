"""Jede Seitenadresse ist auch vor dem Login bekannt (kein "Page not found" beim Neuladen)."""
import re
from pathlib import Path

APP = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")


def test_alle_seitenadressen_vor_dem_login_bekannt():
    adressen = set(re.findall(r'url_path="([a-z_]+)"', APP)) - {"start"}
    liste = re.search(r"SEITEN_PFADE = \[(.*?)\]", APP, re.S).group(1)
    assert adressen == set(re.findall(r'"([a-z_]+)"', liste))
