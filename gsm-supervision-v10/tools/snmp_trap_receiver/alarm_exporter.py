#!/usr/bin/env python3
"""Alarmes d'OMC reçues par traps SNMP -> métriques Prometheus (collecteur textfile de node_exporter).

Lit les traps bruts enregistrés par trap_handler.py, tient à jour la liste des alarmes ACTIVES
(apparition / disparition), et écrit pour node_exporter :

  gsm_ne_active_alarm{vendor, alarm_id, site_id, ne_id, code, severity, description, location}
                                                     = début de l'alarme (horodatage Unix)
  gsm_alarm_receiver_heartbeat_timestamp_seconds     dernier passage de l'exporteur
  gsm_alarm_receiver_last_trap_timestamp_seconds     dernier trap reçu
  gsm_alarm_receiver_active                          nombre d'alarmes actives
  gsm_alarm_receiver_traps                           traps traités par type (raise, clear, ignored, unknown, invalid)
  gsm_alarm_receiver_unknown_trap{trap_oid}          types de traps non reconnus (20 max.)

Aucun OID d'équipementier n'est supposé : la correspondance (OID -> champ, valeurs de gravité,
type apparition / disparition) est écrite à partir des traps RÉELS reçus (mode --inspect) et de
la MIB de l'interface nord fournie par l'équipementier. Les valeurs « A_COMPLETER » bloquent le
démarrage tant qu'elles ne sont pas renseignées.

  python3 alarm_exporter.py --inspect                  # résumé des traps reçus (aide à la configuration)
  python3 alarm_exporter.py --config c.json --dry-run  # rejoue tous les traps reçus, affiche les métriques
  python3 alarm_exporter.py --config c.json            # service (boucle)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:                                  # pragma: no cover
    ZoneInfo = None

log = logging.getLogger("alarm_exporter")
PLACEHOLDER = "A_COMPLETER"
SEVERITIES = {"CRITICAL", "MAJOR", "MINOR", "WARNING", "INDETERMINATE"}
STD_OIDS = {".1.3.6.1.2.1.1.3.0": "sysUpTime.0", ".1.3.6.1.6.3.1.1.4.1.0": "snmpTrapOID.0",
            ".1.3.6.1.6.3.18.1.3.0": "snmpTrapAddress.0", ".1.3.6.1.6.3.18.1.4.0": "snmpTrapCommunity.0",
            ".1.3.6.1.6.3.1.1.4.3.0": "snmpTrapEnterprise.0"}
FIELDS = ("alarm_id", "code", "name", "severity", "ne_name", "location", "occurred")


class ConfigError(ValueError):
    pass


# --------------------------------------------------------------------------- valeurs
def norm_oid(o: str | None) -> str:
    o = (o or "").strip()
    return o if not o or o.startswith(".") else "." + o


def decode(value: str, encodings: list[str]) -> str:
    if not isinstance(value, str) or not value.startswith("hex:"):
        return value
    raw = bytes.fromhex(value[4:])
    for enc in encodings:
        try:
            return raw.decode(enc).replace("\x00", "").strip()
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1").strip()


def hex_bytes(value: str) -> bytes | None:
    return bytes.fromhex(value[4:]) if isinstance(value, str) and value.startswith("hex:") else None


def parse_time(raw: str, encodings: list[str], tz) -> float | None:
    """DateAndTime SNMP binaire (8 ou 11 octets) ou texte (formats usuels), sinon None."""
    b = hex_bytes(raw)
    if b is not None and len(b) in (8, 11):
        try:
            year = int.from_bytes(b[0:2], "big")
            dt = datetime(year, b[2], b[3], b[4], b[5], b[6], b[7] * 100000)
            if len(b) == 11:
                off = timedelta(hours=b[9], minutes=b[10]) * (1 if chr(b[8]) == "+" else -1)
                return dt.replace(tzinfo=timezone(off)).timestamp()
            return dt.replace(tzinfo=tz).timestamp()
        except (ValueError, IndexError):
            pass
    text = decode(raw, encodings)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S", "%d/%m/%Y %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(text.strip()[:26].rstrip("Z"), fmt).replace(tzinfo=tz).timestamp()
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text.strip())
        return (dt if dt.tzinfo else dt.replace(tzinfo=tz)).timestamp()
    except ValueError:
        return None


# --------------------------------------------------------------------------- configuration
def _placeholders(obj, path="") -> list[str]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("_"):
                continue
            if PLACEHOLDER in str(k):
                out.append(f"{path}{k} (clé)")
            out += _placeholders(v, f"{path}{k}.")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _placeholders(v, f"{path}{i}.")
    elif isinstance(obj, str) and PLACEHOLDER in obj:
        out.append(path.rstrip("."))
    return out


def _strip_comments(d):
    if isinstance(d, dict):
        return {k: _strip_comments(v) for k, v in d.items() if not str(k).startswith("_")}
    return d


def load_config(path: str) -> dict:
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Configuration illisible ({path}) : {exc}") from exc
    cfg = _strip_comments(cfg)
    missing = _placeholders(cfg)
    if missing:
        raise ConfigError("Configuration incomplète, à renseigner à partir des traps reçus (--inspect) et de la MIB "
                          f"de l'interface nord : {', '.join(missing)}")
    if str(cfg.get("vendor", "")).lower() not in ("huawei", "ericsson", "zte"):
        raise ConfigError("vendor : huawei, ericsson ou zte")
    cfg["vendor"] = cfg["vendor"].lower()
    f = cfg.get("fields") or {}
    if not f.get("alarm_id"):
        raise ConfigError("fields.alarm_id (numéro unique de l'alarme) est obligatoire")
    if not (f.get("name") or f.get("code")):
        raise ConfigError("fields.name ou fields.code est obligatoire")
    cfg["fields"] = {k: norm_oid(v) for k, v in f.items() if v and k in FIELDS}
    ev = cfg.get("event") or {}
    if ev.get("by") not in ("trap_oid", "varbind"):
        raise ConfigError("event.by : trap_oid (type de trap) ou varbind (valeur d'un champ)")
    if ev["by"] == "varbind" and not ev.get("oid"):
        raise ConfigError("event.oid requis quand event.by = varbind")
    norm = norm_oid if ev["by"] == "trap_oid" else (lambda x: str(x))
    for k in ("raise", "clear", "ignore"):
        ev[k] = {norm(x) for x in ev.get(k) or []}
    if not ev["raise"]:
        raise ConfigError("event.raise : au moins une valeur (traps ou valeurs d'apparition d'alarme)")
    ev["oid"] = norm_oid(ev.get("oid"))
    cfg["event"] = ev
    bad = {k: v for k, v in (cfg.get("severity_map") or {}).items() if str(v).upper() not in SEVERITIES}
    if bad:
        raise ConfigError(f"severity_map : valeurs {', '.join(sorted(SEVERITIES))} uniquement : {bad}")
    cfg["severity_map"] = {str(k).strip().lower(): str(v).upper() for k, v in (cfg.get("severity_map") or {}).items()}
    rx = (cfg.get("site_id") or {}).get("regex")
    if rx:
        try:
            if "site" not in re.compile(rx).groupindex:
                raise ConfigError("site_id.regex doit contenir un groupe nommé (?P<site>...)")
        except re.error as exc:
            raise ConfigError(f"site_id.regex invalide : {exc}") from exc
    return cfg


# --------------------------------------------------------------------------- traitement
class AlarmBook:
    def __init__(self, cfg: dict, state: dict | None = None):
        self.cfg = cfg
        self.enc = cfg.get("encodings") or ["utf-8", "gbk", "latin-1"]
        tzname = cfg.get("timezone", "Africa/Algiers")
        self.tz = ZoneInfo(tzname) if ZoneInfo else timezone.utc
        st = state or {}
        self.active: dict[str, dict] = st.get("active", {})
        self.offsets: dict[str, int] = st.get("offsets", {})
        self.stats: Counter = Counter(st.get("stats", {}))
        self.unknown: Counter = Counter(st.get("unknown", {}))
        self.last_trap: float | None = st.get("last_trap")
        rx = (cfg.get("site_id") or {}).get("regex")
        self.site_rx = re.compile(rx) if rx else None
        self.site_from = (cfg.get("site_id") or {}).get("from") or ["ne_name", "location", "name"]

    def state(self) -> dict:
        return {"active": self.active, "offsets": self.offsets, "stats": dict(self.stats),
                "unknown": dict(self.unknown.most_common(50)), "last_trap": self.last_trap}

    def _field(self, vb: list, key: str) -> str | None:
        oid = self.cfg["fields"].get(key)
        if not oid:
            return None
        for o, v in vb:
            if o == oid or o.startswith(oid + "."):
                return v
        return None

    def process(self, rec: dict) -> str:
        vb = rec.get("vb") or []
        self.last_trap = max(self.last_trap or 0, rec.get("t") or 0)
        ev = self.cfg["event"]
        if ev["by"] == "trap_oid":
            key = norm_oid(rec.get("trap"))
        else:
            raw = next((v for o, v in vb if o == ev["oid"] or o.startswith(ev["oid"] + ".")), None)
            key = decode(raw, self.enc) if raw is not None else None
        if key in ev["ignore"]:
            kind = "ignored"
        elif key in ev["raise"]:
            kind = "raise"
        elif key in ev["clear"]:
            kind = "clear"
        else:
            self.unknown[str(key)] += 1
            self.stats["unknown"] += 1
            return "unknown"
        if kind == "ignored":
            self.stats["ignored"] += 1
            return kind
        raw_id = self._field(vb, "alarm_id")
        if raw_id in (None, ""):
            self.stats["invalid"] += 1
            return "invalid"
        aid = decode(raw_id, self.enc)
        if kind == "clear":
            self.stats["clear"] += 1
            self.active.pop(aid, None)
            return kind
        get = lambda k: (decode(self._field(vb, k), self.enc) if self._field(vb, k) is not None else "")  # noqa: E731
        occurred = None
        if self._field(vb, "occurred") is not None:
            occurred = parse_time(self._field(vb, "occurred"), self.enc, self.tz)
        sev_raw = get("severity")
        severity = self.cfg["severity_map"].get(sev_raw.strip().lower(), "INDETERMINATE") if sev_raw else "INDETERMINATE"
        values = {"ne_name": get("ne_name"), "location": get("location"), "name": get("name")}
        site = ""
        if self.site_rx:
            for src in self.site_from:
                m = self.site_rx.search(values.get(src, "") or "")
                if m:
                    site = m.group("site")
                    break
        self.active[aid] = {
            "alarm_id": aid, "code": get("code"), "name": values["name"], "severity": severity,
            "ne_id": values["ne_name"], "site_id": site, "location": values["location"][:200],
            "raised_at": occurred or rec.get("t") or time.time(), "received_at": rec.get("t"),
        }
        self.stats["raise"] += 1
        return kind

    def expire(self, now: float) -> int:
        days = self.cfg.get("expire_after_days")
        if not days:
            return 0
        limit = now - float(days) * 86400
        old = [k for k, a in self.active.items() if (a.get("received_at") or a["raised_at"]) < limit]
        for k in old:
            del self.active[k]
        return len(old)

    def read_spool(self, spool: Path, max_lines: int = 200000) -> int:
        n = 0
        for f in sorted(spool.glob("traps-*.jsonl")):
            pos = self.offsets.get(f.name, 0)
            size = f.stat().st_size
            if size < pos:
                pos = 0                                   # fichier recréé
            if size == pos:
                continue
            with f.open("rb") as fh:
                fh.seek(pos)
                for raw in fh:
                    if not raw.endswith(b"\n"):          # ligne en cours d'écriture : relue au prochain passage
                        break
                    pos += len(raw)
                    try:
                        self.process(json.loads(raw))
                    except (ValueError, TypeError, KeyError):
                        self.stats["invalid"] += 1
                    n += 1
                    if n >= max_lines:
                        break
            self.offsets[f.name] = pos
            if n >= max_lines:
                break
        return n

    def cleanup(self, spool: Path, keep_days: int) -> None:
        limit = time.time() - keep_days * 86400
        for f in spool.glob("traps-*.jsonl"):
            if f.stat().st_mtime < limit and self.offsets.get(f.name, -1) >= f.stat().st_size:
                f.unlink(missing_ok=True)
                self.offsets.pop(f.name, None)
        known = {f.name for f in spool.glob("traps-*.jsonl")}
        self.offsets = {k: v for k, v in self.offsets.items() if k in known}


# --------------------------------------------------------------------------- sortie
def _esc(v) -> str:
    return str(v).replace("\\", "\\\\").replace("\n", " ").replace('"', '\\"')


def _labels(d: dict) -> str:
    return "{" + ",".join(f'{k}="{_esc(v)}"' for k, v in d.items() if v not in (None, "")) + "}"


def render(book: AlarmBook, now: float) -> str:
    v = {"vendor": book.cfg["vendor"]}
    lines = ["# HELP gsm_ne_active_alarm Alarme active de l'OMC (valeur : début de l'alarme, horodatage Unix).",
             "# TYPE gsm_ne_active_alarm gauge"]
    for a in sorted(book.active.values(), key=lambda x: x["alarm_id"]):
        lab = {**v, "alarm_id": a["alarm_id"], "site_id": a["site_id"], "ne_id": a["ne_id"], "code": a["code"],
               "severity": a["severity"], "description": a["name"][:200], "location": a["location"]}
        lines.append(f"gsm_ne_active_alarm{_labels(lab)} {int(a['raised_at'])}")
    lines += ["# HELP gsm_alarm_receiver_heartbeat_timestamp_seconds Dernier passage de l'exporteur d'alarmes.",
              "# TYPE gsm_alarm_receiver_heartbeat_timestamp_seconds gauge",
              f"gsm_alarm_receiver_heartbeat_timestamp_seconds{_labels(v)} {int(now)}",
              "# HELP gsm_alarm_receiver_active Nombre d'alarmes actives.",
              "# TYPE gsm_alarm_receiver_active gauge",
              f"gsm_alarm_receiver_active{_labels(v)} {len(book.active)}"]
    if book.last_trap:
        lines += ["# HELP gsm_alarm_receiver_last_trap_timestamp_seconds Dernier trap reçu (Unix).",
                  "# TYPE gsm_alarm_receiver_last_trap_timestamp_seconds gauge",
                  f"gsm_alarm_receiver_last_trap_timestamp_seconds{_labels(v)} {int(book.last_trap)}"]
    lines += ["# HELP gsm_alarm_receiver_traps Traps traités depuis la mise en service, par type.",
              "# TYPE gsm_alarm_receiver_traps gauge"]
    for k in ("raise", "clear", "ignored", "unknown", "invalid"):
        lines.append(f"gsm_alarm_receiver_traps{_labels({**v, 'kind': k})} {book.stats.get(k, 0)}")
    if book.unknown:
        lines += ["# HELP gsm_alarm_receiver_unknown_trap Types de traps non reconnus (à classer dans event).",
                  "# TYPE gsm_alarm_receiver_unknown_trap gauge"]
        lines += [f"gsm_alarm_receiver_unknown_trap{_labels({**v, 'trap_oid': k[:120]})} {n}"
                  for k, n in book.unknown.most_common(20)]
    return "\n".join(lines) + "\n"


def write_atomic(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# --------------------------------------------------------------------------- inspection
def inspect(spool: Path, encodings: list[str]) -> None:
    traps: Counter = Counter()
    by_trap: dict[str, Counter] = defaultdict(Counter)
    samples: dict[str, Counter] = defaultdict(Counter)
    sources: Counter = Counter()
    n = 0
    for f in sorted(spool.glob("traps-*.jsonl")):
        for raw in f.open("rb"):
            try:
                rec = json.loads(raw)
            except ValueError:
                continue
            n += 1
            t = rec.get("trap") or "(sans snmpTrapOID : trap SNMPv1 ?)"
            traps[t] += 1
            sources[rec.get("src") or "?"] += 1
            for o, v in rec.get("vb") or []:
                if o in STD_OIDS:
                    continue
                by_trap[t][o] += 1
                samples[o][decode(v, encodings)[:80]] += 1
    if not n:
        print(f"Aucun trap reçu dans {spool}. Vérifier : destination configurée sur l'OMC (IP du serveur, port UDP), "
              "pare-feu, identifiants SNMP (docker compose logs snmp-trap-huawei).")
        return
    print(f"{n} trap(s) reçu(s) — sources : {dict(sources)}\n")
    for t, c in traps.most_common():
        print(f"TYPE DE TRAP {t} : {c} reçu(s)")
        for o, cnt in by_trap[t].most_common():
            vals = samples[o]
            ex = " | ".join(f"{v!r}" for v, _ in vals.most_common(4))
            print(f"   {o}  ({len(vals)} valeur(s) distincte(s))  ex. {ex}")
        print()
    print("Pour remplir la configuration : repérer l'OID du numéro unique de l'alarme (valeurs toutes différentes),\n"
          "du nom de l'alarme, de la gravité (peu de valeurs), du NE, de la localisation, de la date, et les types\n"
          "de traps (ou la valeur d'un champ) qui signalent l'apparition et la disparition d'une alarme.\n"
          "À confirmer avec la MIB de l'interface nord fournie par l'équipementier.")


# --------------------------------------------------------------------------- service
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config")
    ap.add_argument("--spool", default=os.environ.get("TRAP_SPOOL_DIR", "/data/spool"))
    ap.add_argument("--state", default=os.environ.get("ALARM_STATE_FILE", "/data/state/alarms_state.json"))
    ap.add_argument("--inspect", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="Rejouer tous les traps reçus et afficher les métriques")
    ap.add_argument("--interval", type=int, default=10)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    spool = Path(a.spool)
    if a.inspect:
        inspect(spool, ["utf-8", "gbk", "latin-1"])
        return 0
    if not a.config:
        ap.error("--config est obligatoire (ou --inspect)")
    try:
        cfg = load_config(a.config)
    except ConfigError as exc:
        log.error("%s", exc)
        if a.dry_run or os.environ.get("EXIT_ON_CONFIG_ERROR"):
            return 2
        # Service : attendre que la configuration soit complétée (fichier relu chaque minute) ;
        # les traps continuent d'être reçus et conservés entre-temps.
        while True:
            time.sleep(60)
            try:
                cfg = load_config(a.config)
                break
            except ConfigError as exc2:
                log.warning("En attente de configuration : %s", exc2)
    if a.dry_run:
        book = AlarmBook(cfg)
        book.read_spool(spool, max_lines=10**9)
        sys.stdout.write(render(book, time.time()))
        log.info("Traps : %s ; alarmes actives : %d", dict(book.stats), len(book.active))
        return 0
    state_path = Path(a.state)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else None
    except ValueError:
        log.warning("État illisible (%s) : reprise depuis le début des traps conservés", state_path)
        state = None
    book = AlarmBook(cfg, state)
    out = Path((cfg.get("output") or {}).get("dir", "/textfile")) / \
        (cfg.get("output") or {}).get("file", f"gsm_{cfg['vendor']}_alarms.prom")
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
    log.info("Exporteur d'alarmes %s démarré (%d alarme(s) active(s) reprise(s))", cfg["vendor"], len(book.active))
    last_cleanup = 0.0
    while not stop["flag"]:
        started = time.time()
        try:
            n = book.read_spool(spool)
            expired = book.expire(started)
            if n or expired:
                log.info("%d trap(s) traité(s), %d alarme(s) active(s)%s", n, len(book.active),
                         f", {expired} expirée(s)" if expired else "")
            write_atomic(out, render(book, started))
            write_atomic(state_path, json.dumps(book.state(), ensure_ascii=False), 0o600)
            if started - last_cleanup > 3600:
                book.cleanup(spool, int(cfg.get("spool_keep_days", 7)))
                last_cleanup = started
        except Exception:
            log.exception("Erreur inattendue")
        while not stop["flag"] and time.time() - started < a.interval:
            time.sleep(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
