"""Connecteur de DÉMONSTRATION — données 100 % FICTIVES.

Rejoue le fichier de test (data/test/sites_fictifs.csv) et simule des pannes
et rétablissements aléatoires pour faire vivre le prototype (carte, historique,
tableau de bord). Ne jamais activer en production sur des sources réelles.

Configuration (omc_sources.config) :
  dataset            : chemin du CSV fictif (défaut : <DATA_DIR>/test/sites_fictifs.csv)
  p_fail             : probabilité de panne d'une technologie par collecte (défaut 0.002)
  p_recover          : probabilité de rétablissement par collecte (défaut 0.15)
  p_major_alarm      : probabilité d'alarme majeure fictive par site et par collecte (défaut 0.0005)
  seed               : graine aléatoire (optionnelle)
"""
from __future__ import annotations

import os
import random
import threading
from datetime import datetime, timezone
from pathlib import Path

from ...config import get_settings
from ...services.csv_import import parse_sites_csv
from ..model import CollectResult, NAlarm
from .base import BaseConnector, ConnectorNotConfigured

_STATE: dict[str, dict] = {}
_LOCK = threading.Lock()


class DemoConnector(BaseConnector):
    def _dataset(self) -> Path:
        p = self.spec.config.get("dataset") or os.path.join(get_settings().data_dir, "test", "sites_fictifs.csv")
        path = Path(p)
        if not path.is_file():
            raise ConnectorNotConfigured(f"Jeu de données fictif introuvable : {p}")
        return path

    def collect(self) -> CollectResult:
        cfg = self.spec.config
        with _LOCK:
            st = _STATE.get(self.spec.code)
            if st is None:
                results, _ = parse_sites_csv(self._dataset().read_bytes(), default_source=self.spec.code)
                mine = [r for (src, vendor), r in results.items() if src == self.spec.code] or \
                       [r for (src, vendor), r in results.items() if vendor == self.spec.vendor]
                base = CollectResult()
                for r in mine:
                    base.sites += r.sites
                    base.elements += r.elements
                st = {
                    "base": base,
                    "status": {e.external_id: e.oper_status for e in base.elements},
                    "alarms": {},
                    "rng": random.Random(cfg.get("seed")),
                    "seq": 0,
                }
                _STATE[self.spec.code] = st

            rng: random.Random = st["rng"]
            p_fail = float(cfg.get("p_fail", 0.002))
            p_rec = float(cfg.get("p_recover", 0.15))
            p_major = float(cfg.get("p_major_alarm", 0.0005))
            now = datetime.now(timezone.utc)
            base: CollectResult = st["base"]
            res = CollectResult(sites=base.sites, inventory_complete=True, alarms_complete=True,
                                details={"demo": True})
            by_site: dict[str, list] = {}
            for e in base.elements:
                cur = st["status"][e.external_id]
                if cur == "UP" and rng.random() < p_fail:
                    cur = "DOWN"
                elif cur in ("DOWN", "DEGRADED") and rng.random() < p_rec:
                    cur = "UP"
                elif cur == "UNKNOWN" and rng.random() < p_rec / 3:
                    cur = "UP"
                st["status"][e.external_id] = cur
                ne = type(e)(**{**e.__dict__, "oper_status": cur, "raw_status": f"demo:{cur}",
                                "observed_at": now, "extra": {"demo": True}})
                res.elements.append(ne)
                by_site.setdefault(e.site_external_id, []).append(ne)
                key = f"{e.external_id}-LINK"
                if cur == "DOWN":
                    st["alarms"].setdefault(key, NAlarm(
                        external_alarm_id=key, site_external_id=e.site_external_id,
                        element_external_id=e.external_id, alarm_code="DEMO-001",
                        description=f"[FICTIF] Perte de liaison {e.technology}", severity="CRITICAL",
                        raised_at=now))
                else:
                    st["alarms"].pop(key, None)
            for site_ext in list(by_site):
                key = f"{site_ext}-PWR"
                if key in st["alarms"]:
                    if rng.random() < p_rec:
                        st["alarms"].pop(key)
                elif rng.random() < p_major:
                    st["alarms"][key] = NAlarm(
                        external_alarm_id=key, site_external_id=site_ext, alarm_code="DEMO-002",
                        description="[FICTIF] Défaut d'alimentation secteur", severity="MAJOR", raised_at=now)
            res.alarms = list(st["alarms"].values())
            return res
