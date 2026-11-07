"""Exporteur « textfile » (node_exporter) : format d'export FICTIF défini dans le test."""
from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "omc_textfile_exporter", ROOT / "tools" / "omc_textfile_exporter" / "omc_textfile_exporter.py")
ote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ote)

CSV = """# export de test FICTIF
NOM_NE;TYPE_NE;ETAT_LIAISON;RAT
TST_90001_A;TYPE_X;OK;GSM
TST_90001_B;TYPE_Y;OK;LTE
TST_90002_A;TYPE_X;PERDU;GSM
TST_90003_A;TYPE_X;BIZARRE;GSM
TST_90001_A;TYPE_X;OK;GSM
SANS_CODE;TYPE_X;OK;GSM
"""


def config(tmp_path, **over) -> dict:
    cfg = {
        "vendor": "huawei",
        "input": {"dir": str(tmp_path / "in"), "pattern": "etat_*.csv", "max_age_s": 600, "stable_s": 0,
                  "comment_prefix": "#"},
        "columns": {"ne_id": "NOM_NE", "ne_type": "TYPE_NE", "status": "ETAT_LIAISON", "technology": "RAT"},
        "derive": {"site_id_regex": r"_(?P<site>\d{5})_"},
        "status_map": {"_comment_": "x", "ok": 1, "perdu": 0},
        "output": {"dir": str(tmp_path / "out"), "file": "gsm_huawei.prom"},
    }
    cfg.update(over)
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg))
    return ote.load_config(str(p))


def test_export_and_metrics(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "etat_1.csv").write_text(CSV, encoding="utf-8")
    exp = ote.Exporter(config(tmp_path))
    exp.run_once()
    text = (tmp_path / "out" / "gsm_huawei.prom").read_text()
    assert 'gsm_ne_oper_status{vendor="huawei",site_id="90001",ne_id="TST_90001_A",ne_type="TYPE_X",technology="2G"} 1' in text
    assert 'ne_id="TST_90001_B",ne_type="TYPE_Y",technology="4G"} 1' in text
    assert 'ne_id="TST_90002_A",ne_type="TYPE_X",technology="2G"} 0' in text
    assert "TST_90003_A" not in text.split("gsm_exporter_up")[0]          # état inconnu : ignoré
    assert 'gsm_exporter_unmapped_status{vendor="huawei",value="BIZARRE"} 1' in text
    assert 'gsm_exporter_rows{vendor="huawei",result="skipped_duplicate"} 1' in text
    assert 'gsm_exporter_rows{vendor="huawei",result="skipped_no_site"} 1' in text
    assert 'gsm_exporter_up{vendor="huawei"} 1' in text
    assert not [f for f in (tmp_path / "out").iterdir() if f.name.startswith(".tmp_")]


def test_stale_or_missing_export_removes_status_series(tmp_path):
    (tmp_path / "in").mkdir()
    f = tmp_path / "in" / "etat_1.csv"
    f.write_text(CSV, encoding="utf-8")
    exp = ote.Exporter(config(tmp_path))
    exp.run_once()
    old = time.time() - 3600
    os.utime(f, (old, old))                       # l'OMC ne dépose plus de fichier
    exp.run_once()
    text = (tmp_path / "out" / "gsm_huawei.prom").read_text()
    assert "gsm_ne_oper_status" not in text                       # => collecte en ÉCHEC, jamais DOWN
    assert 'gsm_exporter_up{vendor="huawei"} 0' in text
    assert "gsm_exporter_last_success_timestamp_seconds" in text and "trop ancien" in text
    f.unlink()
    assert "gsm_ne_oper_status" not in exp.run_once(write=False)


def test_wrong_column_and_placeholders(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "etat_1.csv").write_text(CSV, encoding="utf-8")
    cfg = config(tmp_path, columns={"ne_id": "NOM_NE", "status": "ETAT", "technology": "RAT"})
    out = ote.Exporter(cfg).run_once(write=False)
    assert "gsm_ne_oper_status" not in out and "ETAT" in out
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"vendor": "huawei", "input": {"dir": "x", "pattern": "A_COMPLETER"},
                             "columns": {"ne_id": "A_COMPLETER", "status": "s"}, "status_map": {"a": 1}}))
    with pytest.raises(ote.ConfigError, match="A_COMPLETER|incomplète"):
        ote.load_config(str(p))
    example = ROOT / "tools" / "omc_textfile_exporter" / "huawei.example.json"
    with pytest.raises(ote.ConfigError, match="incomplète"):
        ote.load_config(str(example))
