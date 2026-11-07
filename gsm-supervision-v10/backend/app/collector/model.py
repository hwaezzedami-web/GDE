"""Modèle de données commun (normalisé) produit par tous les connecteurs.

Chaque connecteur convertit les données spécifiques de son équipementier vers
ces structures ; seul le module d'ingestion (services/ingest.py) écrit en base.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NSite:
    external_id: str                 # code site opérateur (commun à toutes les technologies)
    name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    wilaya_code: int | None = None
    wilaya_name: str | None = None   # utilisé si le code n'est pas fourni
    commune: str | None = None
    address: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class NElement:
    external_id: str                 # identifiant unique de l'équipement/cellule DANS cet OMC
    site_external_id: str
    technology: str                  # '2G' | '3G' | '4G' | '5G'
    element_type: str = "NE"         # BTS, NODEB, ENODEB, GNODEB, CELL…
    name: str | None = None
    oper_status: str | None = None   # 'UP'|'DOWN'|'DEGRADED'|'UNKNOWN' ; None = non fourni par cette collecte
    raw_status: str | None = None    # valeur brute reçue (traçabilité)
    observed_at: datetime | None = None
    last_communication_at: datetime | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class NAlarm:
    external_alarm_id: str
    site_external_id: str | None = None
    element_external_id: str | None = None
    alarm_code: str | None = None
    description: str | None = None
    severity: str = "INDETERMINATE"  # CRITICAL|MAJOR|MINOR|WARNING|INDETERMINATE
    raised_at: datetime | None = None
    cleared_at: datetime | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class CollectResult:
    sites: list[NSite] = field(default_factory=list)
    elements: list[NElement] = field(default_factory=list)
    alarms: list[NAlarm] = field(default_factory=list)
    # True : l'inventaire est complet -> les équipements absents sont désactivés
    inventory_complete: bool = False
    # True : la liste des alarmes actives est complète -> les absentes sont acquittées (CLEARED)
    alarms_complete: bool = False
    rejected: list[str] = field(default_factory=list)   # lignes rejetées (motif)
    warnings: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
