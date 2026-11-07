#!/usr/bin/env python3
"""Exporteur OMC -> Prometheus par le collecteur « textfile » de node_exporter.

Lit le dernier export déposé par un OMC (fichier CSV : liste des équipements et de
leur état), applique une configuration écrite à partir de l'export RÉEL (noms de
colonnes, valeurs d'état), et écrit les métriques du contrat du projet
(docs/10_PROMETHEUS.md) dans un fichier .prom que node_exporter publie :

  gsm_ne_oper_status{vendor, site_id, ne_id, ne_name, ne_type, technology}   1 UP, 0 DOWN, 2 DÉGRADÉ
  gsm_exporter_up{vendor}                                     1 lecture réussie, 0 échec
  gsm_exporter_heartbeat_timestamp_seconds{vendor}            dernier passage du script (vivant ?)
  gsm_exporter_last_success_timestamp_seconds{vendor}         date de la dernière lecture réussie
  gsm_exporter_source_mtime_seconds{vendor}                   date de l'export lu
  gsm_exporter_rows{vendor, result}                           lignes lues / retenues / ignorées
  gsm_exporter_unmapped_status{vendor, value}                 valeurs d'état absentes de la table (20 max.)

Sécurité de la supervision : si l'export est absent, illisible ou trop ancien, le
fichier ne contient plus aucune série d'état (gsm_exporter_up = 0) ; si le script
s'arrête, son battement de cœur vieillit. Dans les deux cas l'application voit une
collecte en ÉCHEC (requête de santé ci-dessous), jamais des sites DOWN :
  gsm_exporter_up{vendor="huawei"} * on(vendor)
    ((time() - gsm_exporter_heartbeat_timestamp_seconds{vendor="huawei"}) < bool 300)

Aucun format d'équipementier n'est supposé : toutes les valeurs « A_COMPLETER » de
la configuration doivent être renseignées à partir de l'export réel (mode --inspect).
Lecture seule : le script ne modifie ni l'OMC ni ses fichiers.

Bibliothèque standard uniquement (Python 3.9+).

  python3 omc_textfile_exporter.py --inspect /chemin/export.csv        # aide à la configuration
  python3 omc_textfile_exporter.py --config huawei.json --dry-run      # affiche les métriques
  python3 omc_textfile_exporter.py --config huawei.json --once         # une écriture
  python3 omc_textfile_exporter.py --config huawei.json                # boucle (service)
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import io
import json
import logging
import os
import re
import signal
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

log = logging.getLogger("omc_textfile_exporter")
PLACEHOLDER = "A_COMPLETER"
TECHNOLOGIES = {"2G": "2G", "3G": "3G", "4G": "4G", "5G": "5G", "GSM": "2G", "UMTS": "3G", "WCDMA": "3G",
                "LTE": "4G", "NR": "5G"}
VALID_STATUS = {0, 1, 2}


class ConfigError(ValueError):
    pass


class SourceError(RuntimeError):
    pass


# --------------------------------------------------------------------------- configuration
def _placeholders(obj, path="") -> list[str]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("_"):
                continue                       # commentaires
            if PLACEHOLDER in str(k):
                out.append(f"{path}{k} (clé)")
            out += _placeholders(v, f"{path}{k}.")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += _placeholders(v, f"{path}{i}.")
    elif isinstance(obj, str) and PLACEHOLDER in obj:
        out.append(path.rstrip("."))
    return out


def load_config(path: str) -> dict:
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Configuration illisible ({path}) : {exc}") from exc
    for key in ("status_map", "technology_map"):
        if isinstance(cfg.get(key), dict):
            cfg[key] = {k: v for k, v in cfg[key].items() if not str(k).startswith("_")}
    missing = _placeholders(cfg)
    if missing:
        raise ConfigError("Configuration incomplète, à renseigner à partir de l'export réel "
                          f"(--inspect) : {', '.join(missing)}")
    vendor = str(cfg.get("vendor", "")).strip().lower()
    if vendor not in ("huawei", "ericsson", "zte"):
        raise ConfigError("vendor : huawei, ericsson ou zte")
    inp = cfg.get("input") or {}
    if not inp.get("dir") or not inp.get("pattern"):
        raise ConfigError("input.dir et input.pattern sont obligatoires")
    td = cfg.get("technology_default")
    if td and not TECHNOLOGIES.get(str(td).upper()):
        raise ConfigError("technology_default : 2G, 3G, 4G ou 5G")
    bad_t = {k: v for k, v in (cfg.get("technology_map") or {}).items() if not TECHNOLOGIES.get(str(v).upper())}
    if bad_t:
        raise ConfigError(f"technology_map : valeurs 2G, 3G, 4G ou 5G uniquement : {bad_t}")
    cols = cfg.get("columns") or {}
    if not cols.get("ne_id") or not cols.get("status"):
        raise ConfigError("columns.ne_id et columns.status sont obligatoires")
    smap = cfg.get("status_map") or {}
    if not smap:
        raise ConfigError("status_map est vide")
    bad = {k: v for k, v in smap.items() if v not in VALID_STATUS}
    if bad:
        raise ConfigError(f"status_map : valeurs 1 (UP), 0 (DOWN) ou 2 (DÉGRADÉ) uniquement : {bad}")
    if not cols.get("site_id") and not (cfg.get("derive") or {}).get("site_id_regex"):
        raise ConfigError("Indiquer columns.site_id ou derive.site_id_regex (code site opérateur)")
    rx = (cfg.get("derive") or {}).get("site_id_regex")
    if rx:
        try:
            if "site" not in re.compile(rx).groupindex:
                raise ConfigError("derive.site_id_regex doit contenir un groupe nommé (?P<site>...)")
        except re.error as exc:
            raise ConfigError(f"derive.site_id_regex invalide : {exc}") from exc
    if not cols.get("technology") and not cfg.get("technology_default"):
        raise ConfigError("Indiquer columns.technology ou technology_default (2G, 3G, 4G ou 5G)")
    cfg["vendor"] = vendor
    return cfg


# --------------------------------------------------------------------------- lecture de l'export
def pick_source(cfg: dict, now: float | None = None) -> Path:
    inp = cfg["input"]
    folder = Path(inp["dir"])
    if not folder.is_dir():
        raise SourceError(f"Répertoire d'export introuvable : {folder}")
    stable = float(inp.get("stable_s", 30))
    now = now or time.time()
    files = [f for f in folder.iterdir()
             if f.is_file() and fnmatch.fnmatch(f.name, inp["pattern"]) and now - f.stat().st_mtime >= stable]
    if not files:
        raise SourceError(f"Aucun fichier « {inp['pattern']} » dans {folder}")
    newest = max(files, key=lambda f: f.stat().st_mtime)
    age = now - newest.stat().st_mtime
    max_age = float(inp.get("max_age_s", 1800))
    if age > max_age:
        raise SourceError(f"Export trop ancien : {newest.name} ({int(age)} s > {int(max_age)} s) — "
                          "l'OMC ne dépose plus de fichier ?")
    return newest


def read_rows(path: Path, inp: dict) -> list[dict]:
    raw = path.read_bytes()
    if len(raw) > int(inp.get("max_bytes", 200 * 1024 * 1024)):
        raise SourceError(f"Fichier trop volumineux : {path.name}")
    text = None
    for enc in [inp.get("encoding", "utf-8-sig"), "utf-8-sig", "cp1252", "latin-1"]:
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    lines = text.splitlines()[int(inp.get("skip_lines", 0)):]
    comment = inp.get("comment_prefix")
    if comment:
        lines = [ln for ln in lines if not ln.lstrip().startswith(comment)]
    body = "\n".join(lines)
    delim = inp.get("delimiter")
    if not delim:
        try:
            delim = csv.Sniffer().sniff(body[:8192], delimiters=";,\t|").delimiter
        except csv.Error:
            delim = ","
    reader = csv.DictReader(io.StringIO(body), delimiter=delim)
    if not reader.fieldnames:
        raise SourceError(f"{path.name} : ligne d'en-tête introuvable")
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k} for r in reader]
    return rows


# --------------------------------------------------------------------------- conversion
def convert(rows: list[dict], cfg: dict) -> tuple[list[dict], Counter, Counter]:
    cols = cfg["columns"]
    for key in ("ne_id", "status"):
        if rows and cols[key] not in rows[0]:
            raise SourceError(f"Colonne « {cols[key]} » ({key}) absente de l'export. "
                              f"Colonnes présentes : {', '.join(list(rows[0])[:30])}")
    fold = bool(cfg.get("status_case_insensitive", True))
    smap = {(k.strip().lower() if fold else k.strip()): v for k, v in cfg["status_map"].items()}
    tmap = {k.strip().lower(): v for k, v in (cfg.get("technology_map") or {}).items()}
    rx = (cfg.get("derive") or {}).get("site_id_regex")
    rx = re.compile(rx) if rx else None
    rx_on = (cfg.get("derive") or {}).get("site_id_from", "ne_id")
    keep = cfg.get("filter") or {}
    stats: Counter = Counter()
    unmapped: Counter = Counter()
    out, seen = [], set()
    for r in rows:
        stats["read"] += 1
        if keep.get("column") and r.get(keep["column"], "") not in keep.get("values", []):
            stats["filtered"] += 1
            continue
        ne = r.get(cols["ne_id"], "")
        if not ne:
            stats["skipped_no_ne"] += 1
            continue
        if ne in seen:
            stats["skipped_duplicate"] += 1
            continue
        raw = r.get(cols["status"], "")
        value = smap.get(raw.lower() if fold else raw)
        if value is None:
            unmapped[raw] += 1
            stats["skipped_status"] += 1
            continue
        tech = None
        if cols.get("technology"):
            t = r.get(cols["technology"], "")
            tech = tmap.get(t.lower()) or t
        tech = TECHNOLOGIES.get(str(tech or cfg.get("technology_default") or "").upper())
        if not tech:
            stats["skipped_technology"] += 1
            continue
        site = r.get(cols["site_id"], "") if cols.get("site_id") else ""
        if not site and rx:
            src = r.get(cols.get("ne_name") or "", "") if rx_on == "ne_name" else ne
            m = rx.search(src or "")
            site = m.group("site") if m else ""
        if not site:
            stats["skipped_no_site"] += 1
            continue
        seen.add(ne)
        out.append({"site_id": site, "ne_id": ne, "ne_name": r.get(cols.get("ne_name") or "", ""),
                    "ne_type": r.get(cols.get("ne_type") or "", ""), "technology": tech, "value": value})
        stats["exported"] += 1
    return out, stats, unmapped


# --------------------------------------------------------------------------- écriture .prom
def _esc(v) -> str:
    return str(v).replace("\\", "\\\\").replace("\n", " ").replace('"', '\\"')


def _labels(d: dict) -> str:
    return "{" + ",".join(f'{k}="{_esc(v)}"' for k, v in d.items() if v not in (None, "")) + "}"


def render(cfg: dict, elements: list[dict] | None, stats: Counter, unmapped: Counter,
           last_success: float | None, source_mtime: float | None, error: str | None) -> str:
    v = {"vendor": cfg["vendor"]}
    lines = []
    if elements is not None:
        lines += ["# HELP gsm_ne_oper_status État opérationnel des équipements (1 UP, 0 DOWN, 2 DÉGRADÉ).",
                  "# TYPE gsm_ne_oper_status gauge"]
        for e in elements:
            lab = {**v, "site_id": e["site_id"], "ne_id": e["ne_id"], "ne_name": e["ne_name"],
                   "ne_type": e["ne_type"], "technology": e["technology"]}
            lines.append(f"gsm_ne_oper_status{_labels(lab)} {e['value']}")
    lines += ["# HELP gsm_exporter_up 1 si le dernier export OMC a été lu correctement.",
              "# TYPE gsm_exporter_up gauge",
              f"gsm_exporter_up{_labels(v)} {0 if error else 1}",
              "# HELP gsm_exporter_heartbeat_timestamp_seconds Dernier passage du script (Unix), réussi ou non.",
              "# TYPE gsm_exporter_heartbeat_timestamp_seconds gauge",
              f"gsm_exporter_heartbeat_timestamp_seconds{_labels(v)} {int(time.time())}"]
    if last_success:
        lines += ["# HELP gsm_exporter_last_success_timestamp_seconds Dernière lecture réussie (Unix).",
                  "# TYPE gsm_exporter_last_success_timestamp_seconds gauge",
                  f"gsm_exporter_last_success_timestamp_seconds{_labels(v)} {int(last_success)}"]
    if source_mtime:
        lines += ["# HELP gsm_exporter_source_mtime_seconds Date de l'export OMC lu (Unix).",
                  "# TYPE gsm_exporter_source_mtime_seconds gauge",
                  f"gsm_exporter_source_mtime_seconds{_labels(v)} {int(source_mtime)}"]
    if stats:
        lines += ["# HELP gsm_exporter_rows Lignes de l'export par résultat.", "# TYPE gsm_exporter_rows gauge"]
        lines += [f"gsm_exporter_rows{_labels({**v, 'result': k})} {n}" for k, n in sorted(stats.items())]
    if unmapped:
        lines += ["# HELP gsm_exporter_unmapped_status Valeurs d'état absentes de status_map (à compléter).",
                  "# TYPE gsm_exporter_unmapped_status gauge"]
        lines += [f"gsm_exporter_unmapped_status{_labels({**v, 'value': k[:60] or '(vide)'})} {n}"
                  for k, n in unmapped.most_common(20)]
    if error:
        lines += ["# HELP gsm_exporter_error Dernière erreur de lecture.", "# TYPE gsm_exporter_error gauge",
                  f"gsm_exporter_error{_labels({**v, 'message': error[:200]})} 1"]
    return "\n".join(lines) + "\n"


def write_atomic(directory: str, name: str, content: str) -> Path:
    """node_exporter peut lire le fichier à tout moment : écriture dans un fichier
    temporaire du même répertoire puis renommage atomique."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".prom.tmp", dir=d)   # ignoré par node_exporter
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp, 0o644)
        os.replace(tmp, d / name)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return d / name


# --------------------------------------------------------------------------- cycle
class Exporter:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.last_success: float | None = None

    def run_once(self, write: bool = True) -> str:
        cfg = self.cfg
        out = cfg.get("output") or {}
        name = out.get("file", f"gsm_{cfg['vendor']}.prom")
        try:
            src = pick_source(cfg)
            mtime = src.stat().st_mtime
            elements, stats, unmapped = convert(read_rows(src, cfg["input"]), cfg)
            min_el = int(cfg.get("min_elements", 1))
            if len(elements) < min_el:
                raise SourceError(f"{len(elements)} équipement(s) exporté(s), minimum {min_el} "
                                  f"(lignes : {dict(stats)}) — vérifier status_map et les colonnes")
            self.last_success = time.time()
            content = render(cfg, elements, stats, unmapped, self.last_success, mtime, None)
            log.info("%s : %d équipement(s) exporté(s) depuis %s %s", cfg["vendor"], len(elements), src.name,
                     dict(stats))
            if unmapped:
                log.warning("Valeurs d'état non reconnues (à ajouter dans status_map) : %s",
                            dict(unmapped.most_common(10)))
        except (SourceError, OSError, csv.Error) as exc:
            # Aucune série d'état : l'application verra une collecte en échec, pas des sites DOWN
            content = render(cfg, None, Counter(), Counter(), self.last_success, None, str(exc))
            log.error("%s : %s", cfg["vendor"], exc)
        if write:
            write_atomic(out.get("dir", "/textfile"), name, content)
        return content


def inspect(path: str, delimiter: str | None, skip: int) -> None:
    """Aide à la configuration : colonnes et valeurs distinctes de l'export réel."""
    inp = {"delimiter": delimiter, "skip_lines": skip}
    rows = read_rows(Path(path), inp)
    if not rows:
        print("Aucune ligne de données.")
        return
    cols = list(rows[0])
    print(f"{len(rows)} ligne(s), {len(cols)} colonne(s)\n")
    for c in cols:
        vals = Counter(r.get(c, "") for r in rows)
        sample = ", ".join(f"{v!r}×{n}" for v, n in vals.most_common(8))
        few = len(vals) <= 15 and len(vals) <= max(2, len(rows) // 3)
        kind = "peu de valeurs → candidate pour l'état / la technologie / le type" if few else "identifiant / texte"
        print(f"- {c!r} : {len(vals)} valeur(s) distincte(s) ({kind})\n    {sample}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", help="Fichier de configuration JSON")
    ap.add_argument("--once", action="store_true", help="Une seule lecture puis arrêt")
    ap.add_argument("--dry-run", action="store_true", help="Afficher les métriques sans écrire le fichier")
    ap.add_argument("--interval", type=int, help="Secondes entre deux lectures (défaut : configuration ou 60)")
    ap.add_argument("--inspect", metavar="EXPORT", help="Analyser un export réel pour écrire la configuration")
    ap.add_argument("--delimiter")
    ap.add_argument("--skip-lines", type=int, default=0)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if a.inspect:
        inspect(a.inspect, a.delimiter, a.skip_lines)
        return 0
    if not a.config:
        ap.error("--config est obligatoire (ou --inspect)")
    try:
        cfg = load_config(a.config)
    except ConfigError as exc:
        log.error("%s", exc)
        return 2
    exp = Exporter(cfg)
    if a.dry_run:
        sys.stdout.write(exp.run_once(write=False))
        return 0
    if a.once:
        exp.run_once()
        return 0
    interval = a.interval or int(cfg.get("interval_s", 60))
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
    log.info("Démarrage (%s, toutes les %d s)", cfg["vendor"], interval)
    while not stop["flag"]:
        started = time.time()
        try:
            exp.run_once()
        except Exception:                      # ne jamais arrêter le service sur une erreur imprévue
            log.exception("Erreur inattendue")
        while not stop["flag"] and time.time() - started < interval:
            time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
