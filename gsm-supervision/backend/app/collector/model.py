"""Modèle neutre des données collectées, commun à tous les connecteurs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NSite:
    """Site tel que remonté par un OMC (code OMC brut, avant rapprochement)."""

    external_id: str
    name: str | None = None
    lat: float | None = None
    lon: float | None = None
    wilaya_code: int | None = None
    commune: str | None = None
    address: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class NElement:
    """Élément de réseau (NE) ; ``raw_status`` est la valeur brute de l'OMC."""

    ne_id: str
    site_id: str
    raw_status: str | None
    ne_name: str | None = None
    ne_type: str | None = None
    technology: str = "OTHER"
    observed_at: datetime | None = None  # défaut : CollectResult.observed_at
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class NAlarm:
    alarm_id: str
    site_id: str | None
    ne_id: str | None = None
    code: str | None = None
    severity: str = "INDETERMINATE"
    description: str | None = None
    raised_at: datetime | None = None
    cleared_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CollectResult:
    """Résultat d'une collecte.

    ``observed_at`` est la date des données (date du fichier, de la requête…), pas l'heure de lecture.
    ``elements_complete`` / ``alarms_complete`` : le résultat est un instantané complet de la source ;
    les éléments absents sont désactivés et les alarmes absentes sont terminées.
    """

    observed_at: datetime
    sites: list[NSite] = field(default_factory=list)
    elements: list[NElement] = field(default_factory=list)
    alarms: list[NAlarm] = field(default_factory=list)
    elements_complete: bool = True
    alarms_complete: bool = True
    warnings: list[str] = field(default_factory=list)
