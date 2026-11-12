"""Upload-Grenze im Streamlit-Feld (config.toml) und in der App müssen gleich sein."""
import re
import tomllib
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]


def test_upload_grenze_config_gleich_app():
    config = tomllib.loads((WURZEL / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    app = (WURZEL / "app.py").read_text(encoding="utf-8")
    app_mb = int(re.search(r"^UPLOAD_MAX_MB\s*=\s*(\d+)", app, re.M).group(1))
    assert config["server"]["maxUploadSize"] == app_mb == 20
