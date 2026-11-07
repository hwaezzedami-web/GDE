"""Connecteur de démonstration : données entièrement fictives, déterministes (graine).

Les sites, positions et alarmes sont inventés. Aucune donnée d'opérateur n'est utilisée.
Options de configuration :
  sites                 nombre de sites (défaut 40)
  seed                  graine du générateur (défaut 42)
  observed_offset_s     âge des données remontées, en secondes (défaut 0)
  simulate_failure      true : la collecte échoue (teste la règle « perte de collecte ≠ panne »)
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from ..model import CollectResult, NAlarm, NElement, NSite
from .base import Connector, ConnectorError, SourceSpec, ensure_configured

# Centres fictifs (code wilaya, nom, latitude, longitude) pour répartir les sites.
DEMO_CENTERS = [
    (16, "Alger", 36.75, 3.06),
    (31, "Oran", 35.70, -0.63),
    (25, "Constantine", 36.37, 6.61),
    (23, "Annaba", 36.90, 7.77),
    (19, "Sétif", 36.19, 5.41),
    (9, "Blida", 36.47, 2.83),
    (7, "Biskra", 34.85, 5.73),
    (30, "Ouargla", 31.95, 5.33),
    (11, "Tamanrasset", 22.79, 5.52),
]
TECHNOLOGIES = ("2G", "3G", "4G")
RAW_CHOICES = ("1", "0", "2")  # 1 = UP, 0 = DOWN, 2 = dégradé (voir value_maps de la démo)
RAW_WEIGHTS = (85, 5, 10)


class DemoConnector(Connector):
    name = "demo"

    def collect(self, spec: SourceSpec, now: datetime) -> CollectResult:
        ensure_configured(spec.config)
        config = spec.config
        if config.get("simulate_failure"):
            raise ConnectorError("Panne simulée de la source de démonstration")

        rng = random.Random(int(config.get("seed", 42)))
        count = int(config.get("sites", 40))
        observed = now - timedelta(seconds=int(config.get("observed_offset_s", 0)))
        result = CollectResult(observed_at=observed)

        for index in range(count):
            wilaya, town, lat, lon = DEMO_CENTERS[index % len(DEMO_CENTERS)]
            code = f"{wilaya:02d}{index + 1:04d}"
            result.sites.append(
                NSite(
                    external_id=code,
                    name=f"Site démo {code}",
                    lat=round(lat + rng.uniform(-0.3, 0.3), 6),
                    lon=round(lon + rng.uniform(-0.3, 0.3), 6),
                    wilaya_code=wilaya,
                    commune=town,
                )
            )
            for tech in rng.sample(TECHNOLOGIES, k=rng.randint(1, len(TECHNOLOGIES))):
                ne_id = f"{code}-{tech}"
                raw = rng.choices(RAW_CHOICES, weights=RAW_WEIGHTS)[0]
                result.elements.append(
                    NElement(
                        ne_id=ne_id,
                        site_id=code,
                        raw_status=raw,
                        ne_name=f"{code}-{tech}",
                        ne_type="BTS" if tech == "2G" else "NodeB" if tech == "3G" else "eNodeB",
                        technology=tech,
                    )
                )
                if raw in ("0", "2"):
                    result.alarms.append(
                        NAlarm(
                            alarm_id=f"DEMO-{ne_id}",
                            site_id=code,
                            ne_id=ne_id,
                            code="NODEB_UNAVAILABLE" if raw == "0" else "CELL_DEGRADED",
                            severity="MAJOR" if raw == "0" else "MINOR",
                            description="Alarme fictive (démonstration)",
                            raised_at=observed,
                        )
                    )
        return result
