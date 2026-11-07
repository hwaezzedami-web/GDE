"""Fonctions de normalisation communes aux connecteurs.

Les correspondances par défaut ci-dessous ne couvrent que des valeurs
génériques. Les valeurs réelles propres à chaque OMC DOIVENT être déclarées
dans la configuration de la source (config.value_maps), après analyse des
exports réels — voir docs/04_CONNECTEURS_OMC.md.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

GENERIC_STATUS = {
    "UP": "UP", "DOWN": "DOWN", "DEGRADED": "DEGRADED", "UNKNOWN": "UNKNOWN",
    "OK": "UP", "KO": "DOWN",
}
GENERIC_SEVERITY = {
    "CRITICAL": "CRITICAL", "MAJOR": "MAJOR", "MINOR": "MINOR",
    "WARNING": "WARNING", "INDETERMINATE": "INDETERMINATE",
}
GENERIC_TECH = {
    "2G": "2G", "GSM": "2G",
    "3G": "3G", "UMTS": "3G", "WCDMA": "3G",
    "4G": "4G", "LTE": "4G",
    "5G": "5G", "NR": "5G",
}


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_key(s: str | None) -> str:
    """Clé de comparaison : majuscules, sans accents, sans ponctuation."""
    if s is None:
        return ""
    s = strip_accents(str(s)).upper()
    return re.sub(r"[^A-Z0-9]+", "", s)


def map_value(value, custom: dict | None, generic: dict) -> str | None:
    """Traduit une valeur brute via la table de la source puis la table générique."""
    if value is None:
        return None
    raw = str(value).strip()
    if raw == "":
        return None
    if custom:
        if raw in custom:
            return custom[raw]
        up = {str(k).strip().upper(): v for k, v in custom.items()}
        if raw.upper() in up:
            return up[raw.upper()]
    return generic.get(raw.upper())


def map_status(value, custom: dict | None = None) -> str | None:
    return map_value(value, custom, GENERIC_STATUS)


def map_severity(value, custom: dict | None = None) -> str:
    return map_value(value, custom, GENERIC_SEVERITY) or "INDETERMINATE"


def map_technology(value, custom: dict | None = None) -> str | None:
    return map_value(value, custom, GENERIC_TECH)


def parse_datetime(value, fmt: str | None = None, tz: str = "Africa/Algiers") -> datetime | None:
    """Analyse un horodatage. Sans fuseau explicite, on applique `tz` (heure locale de l'OMC)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip()
        if not s:
            return None
        if fmt:
            dt = datetime.strptime(s, fmt)
        else:
            if re.fullmatch(r"\d{10}(\.\d+)?", s):          # horodatage Unix
                return datetime.fromtimestamp(float(s), tz=timezone.utc)
            s = re.sub(r"(\.\d{6})\d+", r"\1", s)       # nanosecondes -> microsecondes
            dt = datetime.fromisoformat(s.replace("Z", "+00:00").replace("/", "-"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.astimezone(timezone.utc)


def parse_float(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", ".")
    if not s:
        return None
    return float(s)


def split_list(value, seps: str = "|;,/ ") -> list[str]:
    if value is None:
        return []
    return [p for p in re.split("[" + re.escape(seps) + "]+", str(value).strip()) if p]
