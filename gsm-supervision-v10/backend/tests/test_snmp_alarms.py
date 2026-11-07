"""Réception d'alarmes par traps SNMP : OID FICTIFS (1.3.6.1.4.1.99999), aucun format d'équipementier."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "tools" / "snmp_trap_receiver"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


th = _load("trap_handler")
ax = _load("alarm_exporter")
E = ".1.3.6.1.4.1.99999"


def hexs(s: str) -> str:
    return '"' + " ".join(f"{b:02X}" for b in s.encode()) + ' "'


def trap_lines(trap_oid, **vb) -> list[str]:
    lines = ["localhost", "UDP: [10.9.9.9]:40000->[172.18.0.5]:1162", ".1.3.6.1.2.1.1.3.0 0:0:01:00.00",
             f".1.3.6.1.6.3.1.1.4.1.0 {trap_oid}"]
    for k, v in vb.items():
        h = hexs(v)
        parts = h.split(" ")
        # Net-SNMP coupe les longues chaînes hexadécimales en lignes de 16 octets
        first, rest = " ".join(parts[:16]), [" ".join(parts[i:i + 16]) for i in range(16, len(parts), 16)]
        lines.append(f"{E}.1.{k[1:]} {first}")
        lines += rest
    return lines


CFG = {"vendor": "huawei", "event": {"by": "trap_oid", "raise": [f"{E}.0.1"], "clear": [f"{E}.0.2"], "ignore": [f"{E}.0.9"]},
       "fields": {"alarm_id": f"{E}.1.1", "name": f"{E}.1.2", "severity": f"{E}.1.3", "ne_name": f"{E}.1.4",
                  "occurred": f"{E}.1.6"},
       "severity_map": {"_comment_": "x", "critique": "CRITICAL"},
       "site_id": {"regex": r"(?<![0-9])(?P<site>[0-9]{5})(?![0-9])", "from": ["ne_name"]}}


def config(tmp_path, **over):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({**CFG, **over}))
    return ax.load_config(str(p))


def test_handler_parse_and_filter(monkeypatch):
    rec = th.parse(trap_lines(f"{E}.0.1", v1="1001", v2="NodeB Unavailable — très long libellé d'alarme accentué"))
    assert rec["src"] == "10.9.9.9" and rec["trap"] == f"{E}.0.1"
    assert ax.decode(dict(rec["vb"])[f"{E}.1.2"], ["utf-8"]) == "NodeB Unavailable — très long libellé d'alarme accentué"
    monkeypatch.setenv("SNMP_ALLOWED_SOURCES", "10.0.0.0/8, 192.168.1.5")
    assert th.allowed("10.9.9.9") and th.allowed("192.168.1.5") and not th.allowed("172.16.0.1")
    monkeypatch.setenv("SNMP_ALLOWED_SOURCES", "")
    assert th.allowed("172.16.0.1")


def test_raise_clear_and_metrics(tmp_path):
    spool = tmp_path / "spool"
    spool.mkdir()
    traps = [
        th.parse(trap_lines(f"{E}.0.1", v1="A1", v2="NodeB Unavailable", v3="Critique", v4="NodeB Name=3G_17749",
                            v6="2026-11-03 09:02:47")),
        th.parse(trap_lines(f"{E}.0.1", v1="A2", v2="OML Fault", v3="inconnue", v4="HASSIM/A55771")),
        th.parse(trap_lines(f"{E}.0.9", v1="hb")),
        th.parse(trap_lines(f"{E}.0.7", v1="?")),
        th.parse(trap_lines(f"{E}.0.2", v1="A2")),
    ]
    f = spool / "traps-20261103.jsonl"
    f.write_text("".join(json.dumps(t) + "\n" for t in traps) + '{"partiel"')       # ligne en cours d'écriture
    book = ax.AlarmBook(config(tmp_path))
    assert book.read_spool(spool) == 5
    assert set(book.active) == {"A1"} and book.active["A1"]["site_id"] == "17749"
    assert book.active["A1"]["severity"] == "CRITICAL"
    assert book.stats == {"raise": 2, "clear": 1, "ignored": 1, "unknown": 1}
    out = ax.render(book, 0)
    assert 'gsm_ne_active_alarm{vendor="huawei",alarm_id="A1",site_id="17749",ne_id="NodeB Name=3G_17749",' \
           'severity="CRITICAL",description="NodeB Unavailable"} 1793692967' in out          # 08:02:47 UTC
    assert f'gsm_alarm_receiver_unknown_trap{{vendor="huawei",trap_oid="{E}.0.7"}} 1' in out
    # Reprise après redémarrage : état conservé, la ligne partielle complétée est lue une seule fois
    with f.open("a") as fh:
        fh.write("\n")
    book2 = ax.AlarmBook(book.cfg, json.loads(json.dumps(book.state())))
    assert book2.read_spool(spool) == 1 and book2.stats["invalid"] == 1 and set(book2.active) == {"A1"}


def test_dateandtime_and_config_errors(tmp_path):
    # DateAndTime SNMP : 2026-11-03 09:02:47.0 +01:00
    raw = "hex:" + bytes([0x07, 0xEA, 11, 3, 9, 2, 47, 0, ord("+"), 1, 0]).hex().upper()
    assert ax.parse_time(raw, ["utf-8"], None) == 1793692967
    with pytest.raises(ax.ConfigError, match="incomplète"):
        ax.load_config(str(ROOT / "huawei_snmp.example.json"))
    with pytest.raises(ax.ConfigError, match="severity_map"):
        config(tmp_path, severity_map={"x": "GRAVE"})
