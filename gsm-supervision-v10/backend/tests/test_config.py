"""La configuration d'exemple (.env.example) doit être chargeable telle quelle."""
from pathlib import Path

from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def _env_file(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def test_env_example_loads(monkeypatch):
    env = _env_file(ROOT / ".env.example")
    assert "CORS_ORIGINS" in env and env["CORS_ORIGINS"] == ""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("JWT_SECRET", "x" * 64)
    s = Settings(_env_file=None)
    assert s.environment == "production" and s.cors_origin_list == []
    s.check_production()
    monkeypatch.setenv("CORS_ORIGINS", "https://a.intranet, https://b.intranet")
    assert Settings(_env_file=None).cors_origin_list == ["https://a.intranet", "https://b.intranet"]
