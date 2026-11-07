"""Connecteur générique « fichiers d'export » (CSV) — répertoire local/monté ou SFTP.

Usage typique : l'OMC dépose périodiquement des exports (inventaire, états,
alarmes actives) ; le connecteur lit le fichier le plus récent de chaque type.

Point clé de fiabilité : l'horodatage d'observation par défaut est la date de
modification du FICHIER (et non l'heure de lecture). Si l'OMC cesse de produire
des exports, les données vieillissent et passent UNKNOWN au lieu de rester
faussement « fraîches ».

Exemple de configuration : docs/04_CONNECTEURS_OMC.md et collector/profiles/.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone

from ..mapping import TabularMapper, ensure_configured
from ..model import CollectResult
from ..transports.files import make_fetcher
from .base import BaseConnector, ConnectorError

log = logging.getLogger(__name__)

MAX_FILE_BYTES = 500 * 1024 * 1024


def read_csv_rows(data: bytes, csv_cfg: dict) -> list[dict]:
    enc = csv_cfg.get("encoding", "utf-8-sig")
    text_data = data.decode(enc, errors="replace")
    lines = text_data.splitlines()
    skip = int(csv_cfg.get("skip_rows", 0))
    if skip:
        text_data = "\n".join(lines[skip:])
    delim = csv_cfg.get("delimiter")
    if not delim:
        try:
            delim = csv.Sniffer().sniff(text_data[:4096], delimiters=";,\t|").delimiter
        except csv.Error:
            delim = ","
    reader = csv.DictReader(io.StringIO(text_data), delimiter=delim,
                            quotechar=csv_cfg.get("quotechar", '"'))
    return [{(k or "").strip(): v for k, v in row.items()} for row in reader]


class FileExportConnector(BaseConnector):
    def collect(self) -> CollectResult:
        cfg = self.spec.config
        ensure_configured(cfg)
        files_cfg = cfg.get("files") or {}
        if "inventory" not in files_cfg and "status" not in files_cfg:
            raise ConnectorError("Aucun fichier configuré (files.inventory / files.status)", transient=False)
        mapper = TabularMapper(cfg)
        max_age = cfg.get("max_file_age_s")
        res = CollectResult(inventory_complete=bool(cfg.get("inventory_complete", True)),
                            alarms_complete=bool(cfg.get("alarms_complete", True)))
        fetcher = make_fetcher(self.spec.code, cfg)
        try:
            now = datetime.now(timezone.utc)
            for dataset in ("inventory", "status", "alarms"):
                fc = files_cfg.get(dataset)
                if not fc:
                    if dataset == "inventory":
                        res.inventory_complete = False
                    if dataset == "alarms":
                        res.alarms_complete = False
                    continue
                f = fetcher.latest(fc["pattern"])
                if f is None:
                    if fc.get("required", dataset != "alarms"):
                        raise ConnectorError(f"Aucun fichier « {fc['pattern']} » trouvé", transient=True)
                    if dataset == "alarms":
                        res.alarms_complete = False
                    continue
                age = (now - f.mtime).total_seconds()
                if max_age and age > max_age:
                    raise ConnectorError(
                        f"Export {f.name} trop ancien ({int(age)} s > {max_age} s) : l'OMC ne produit plus "
                        "d'exports ? Les données existantes vieilliront jusqu'à l'état UNKNOWN.", transient=True)
                rows = read_csv_rows(fetcher.read(f.name, MAX_FILE_BYTES), cfg.get("csv") or {})
                res.details[dataset] = {"file": f.name, "mtime": f.mtime.isoformat(), "rows": len(rows)}
                if dataset == "inventory":
                    mapper.map_inventory(rows, res, f.mtime)
                elif dataset == "status":
                    mapper.map_status(rows, res, f.mtime)
                else:
                    mapper.map_alarms(rows, res)
        finally:
            fetcher.close()
        return res
