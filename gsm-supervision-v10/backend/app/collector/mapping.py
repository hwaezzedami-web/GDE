"""Conversion de lignes tabulaires (CSV d'export, résultats SQL) vers le modèle commun.

La correspondance colonnes -> champs normalisés est décrite dans la
configuration de la source (clé `columns`). Rien n'est supposé sur les noms de
colonnes des OMC : ils doivent être renseignés à partir des exports réels.

Champs normalisés reconnus par jeu de données :
  inventory : site_id, site_name, latitude, longitude, wilaya_code, wilaya, commune, address,
              element_id, element_name, technology, element_type,
              (optionnel) status, observed_at, last_communication
  status    : element_id | (site_id + technology), status, observed_at, last_communication
  alarms    : alarm_id, element_id, site_id, code, description, severity, raised_at, cleared_at
"""
from __future__ import annotations

import re
from datetime import datetime

from .connectors.base import ConnectorNotConfigured
from .model import CollectResult, NAlarm, NElement, NSite
from .normalize import map_severity, map_status, map_technology, map_value, parse_datetime, parse_float

PLACEHOLDER = "A_COMPLETER"


def find_placeholders(cfg, path: str = "") -> list[str]:
    out = []
    if isinstance(cfg, dict):
        for k, v in cfg.items():
            out += find_placeholders(v, f"{path}{k}.")
    elif isinstance(cfg, list):
        for i, v in enumerate(cfg):
            out += find_placeholders(v, f"{path}{i}.")
    elif isinstance(cfg, str) and PLACEHOLDER in cfg:
        out.append(path.rstrip("."))
    return out


def ensure_configured(cfg: dict) -> None:
    """Refuse de s'exécuter tant qu'une valeur utile vaut A_COMPLETER.

    Les sections du transport non utilisé sont ignorées. Un champ de colonne
    sans objet doit être explicitement mis à null dans la configuration.
    """
    relevant = dict(cfg)
    transport = cfg.get("transport", "local")
    for section in ("local", "sftp"):
        if section != transport:
            relevant.pop(section, None)
    ph = find_placeholders(relevant)
    if ph:
        raise ConnectorNotConfigured(
            "Configuration à compléter à partir des exports réels de l'OMC (valeurs A_COMPLETER) : "
            + ", ".join(ph[:15]) + (" …" if len(ph) > 15 else ""))


class TabularMapper:
    def __init__(self, config: dict):
        self.cfg = config
        self.cols: dict[str, dict[str, str]] = config.get("columns") or {}
        vm = config.get("value_maps") or {}
        self.status_map = vm.get("status") or {}
        self.severity_map = vm.get("severity") or {}
        self.tech_map = vm.get("technology") or {}
        self.type_tech_map = vm.get("element_type_technology") or {}
        ts = config.get("timestamps") or {}
        self.ts_format = ts.get("format")
        self.ts_tz = ts.get("timezone", "Africa/Algiers")
        derive = config.get("derive") or {}
        rx = derive.get("site_id_regex")
        self.site_rx = re.compile(rx) if rx else None
        self.extra_cols = config.get("extra_columns") or []

    # ---------------------------------------------------------------- helpers
    def _get(self, row: dict, dataset: str, field: str):
        col = self.cols.get(dataset, {}).get(field)
        if not col:
            return None
        v = row.get(col)
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v

    def _ts(self, v) -> datetime | None:
        try:
            return parse_datetime(v, self.ts_format, self.ts_tz)
        except (ValueError, TypeError):
            return None

    def _site_id(self, row: dict, dataset: str) -> str | None:
        sid = self._get(row, dataset, "site_id")
        if sid:
            return str(sid)
        if self.site_rx:
            for f in ("element_id", "element_name"):
                v = self._get(row, dataset, f)
                if v:
                    m = self.site_rx.search(str(v))
                    if m:
                        return m.group("site") if "site" in m.groupdict() else m.group(0)
        return None

    def _tech(self, row: dict, dataset: str) -> str | None:
        t = map_technology(self._get(row, dataset, "technology"), self.tech_map)
        if t:
            return t
        et = self._get(row, dataset, "element_type")
        if et:
            return map_value(et, self.type_tech_map, {}) or map_technology(et, self.tech_map)
        return None

    def _element_id(self, row: dict, dataset: str, site_id: str | None, tech: str | None) -> str | None:
        eid = self._get(row, dataset, "element_id")
        if eid:
            return str(eid)
        if site_id and tech:
            return f"{site_id}-{tech}"
        return None

    def _extra(self, row: dict) -> dict:
        return {c: row.get(c) for c in self.extra_cols if row.get(c) not in (None, "")}

    # ---------------------------------------------------------------- jeux de données
    def map_inventory(self, rows: list[dict], res: CollectResult, default_observed: datetime) -> None:
        sites: dict[str, NSite] = {s.external_id: s for s in res.sites}
        for i, row in enumerate(rows, start=1):
            sid = self._site_id(row, "inventory")
            if not sid:
                res.rejected.append(f"inventaire ligne {i} : code site introuvable")
                continue
            if sid not in sites:
                try:
                    lat = parse_float(self._get(row, "inventory", "latitude"))
                    lon = parse_float(self._get(row, "inventory", "longitude"))
                except ValueError:
                    lat = lon = None
                    res.warnings.append(f"inventaire ligne {i} : coordonnées illisibles pour {sid}")
                wc = self._get(row, "inventory", "wilaya_code")
                sites[sid] = NSite(
                    external_id=sid, name=self._get(row, "inventory", "site_name"),
                    latitude=lat, longitude=lon,
                    wilaya_code=int(wc) if wc is not None and str(wc).isdigit() else None,
                    wilaya_name=self._get(row, "inventory", "wilaya"),
                    commune=self._get(row, "inventory", "commune"),
                    address=self._get(row, "inventory", "address"),
                )
            tech = self._tech(row, "inventory")
            eid = self._element_id(row, "inventory", sid, tech)
            if not tech:
                res.rejected.append(f"inventaire ligne {i} : technologie non déterminée pour {eid or sid}")
                continue
            if not eid:
                res.rejected.append(f"inventaire ligne {i} : identifiant d'équipement manquant")
                continue
            raw = self._get(row, "inventory", "status")
            res.elements.append(NElement(
                external_id=eid, site_external_id=sid, technology=tech,
                element_type=self._get(row, "inventory", "element_type") or "NE",
                name=self._get(row, "inventory", "element_name"),
                oper_status=(map_status(raw, self.status_map) or "UNKNOWN") if raw is not None else None,
                raw_status=str(raw) if raw is not None else None,
                observed_at=(self._ts(self._get(row, "inventory", "observed_at")) or default_observed)
                if raw is not None else None,
                last_communication_at=self._ts(self._get(row, "inventory", "last_communication")),
                extra=self._extra(row),
            ))
        res.sites = list(sites.values())

    def map_status(self, rows: list[dict], res: CollectResult, default_observed: datetime) -> None:
        by_id = {e.external_id: e for e in res.elements}
        for i, row in enumerate(rows, start=1):
            sid = self._site_id(row, "status")
            tech = self._tech(row, "status")
            eid = self._element_id(row, "status", sid, tech)
            if not eid:
                res.rejected.append(f"état ligne {i} : équipement non identifié")
                continue
            raw = self._get(row, "status", "status")
            st = map_status(raw, self.status_map)
            if st is None:
                res.warnings.append(f"état ligne {i} : valeur {raw!r} non reconnue -> UNKNOWN (ajouter à value_maps.status)")
                st = "UNKNOWN"
            obs = self._ts(self._get(row, "status", "observed_at")) or default_observed
            lastcomm = self._ts(self._get(row, "status", "last_communication"))
            if eid in by_id:
                e = by_id[eid]
                e.oper_status, e.raw_status, e.observed_at = st, str(raw), obs
                e.last_communication_at = lastcomm or e.last_communication_at
            elif sid and tech:
                e = NElement(external_id=eid, site_external_id=sid, technology=tech, oper_status=st,
                             raw_status=str(raw), observed_at=obs, last_communication_at=lastcomm,
                             element_type=self._get(row, "status", "element_type") or "NE",
                             name=self._get(row, "status", "element_name"), extra=self._extra(row))
                res.elements.append(e)
                by_id[eid] = e
            else:
                res.rejected.append(f"état ligne {i} : équipement {eid} absent de l'inventaire")

    def map_alarms(self, rows: list[dict], res: CollectResult) -> None:
        elem_site = {e.external_id: e.site_external_id for e in res.elements}
        for i, row in enumerate(rows, start=1):
            aid = self._get(row, "alarms", "alarm_id")
            if not aid:
                res.rejected.append(f"alarme ligne {i} : identifiant manquant")
                continue
            eid = self._get(row, "alarms", "element_id")
            sid = self._site_id(row, "alarms") or (elem_site.get(str(eid)) if eid else None)
            res.alarms.append(NAlarm(
                external_alarm_id=str(aid), site_external_id=sid,
                element_external_id=str(eid) if eid else None,
                alarm_code=str(self._get(row, "alarms", "code") or "") or None,
                description=self._get(row, "alarms", "description"),
                severity=map_severity(self._get(row, "alarms", "severity"), self.severity_map),
                raised_at=self._ts(self._get(row, "alarms", "raised_at")),
                cleared_at=self._ts(self._get(row, "alarms", "cleared_at")),
                extra=self._extra(row),
            ))
