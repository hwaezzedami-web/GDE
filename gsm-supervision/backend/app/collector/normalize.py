"""Normalisations génériques (technologie, gravité), indépendantes des équipementiers."""

from __future__ import annotations

TECHNOLOGIES = ("2G", "3G", "4G", "5G")
# Équivalences de normes 3GPP (pas de vocabulaire propre à un équipementier).
_TECH_ALIASES = {"GSM": "2G", "UMTS": "3G", "WCDMA": "3G", "LTE": "4G", "NR": "5G"}

SEVERITIES = ("CRITICAL", "MAJOR", "MINOR", "WARNING", "INDETERMINATE")


def normalize_technology(value: str | None) -> str:
    if not value:
        return "OTHER"
    key = value.strip().upper()
    if key in TECHNOLOGIES:
        return key
    return _TECH_ALIASES.get(key, "OTHER")


def normalize_severity(value: str | None, severity_map: dict[str, str] | None = None) -> str:
    """Traduit une gravité ; ``severity_map`` (source) d'abord, puis les libellés X.733 standard."""
    if value is None:
        return "INDETERMINATE"
    raw = str(value).strip()
    if severity_map:
        mapped = severity_map.get(raw) or severity_map.get(raw.upper())
        if mapped and mapped.upper() in SEVERITIES:
            return mapped.upper()
    upper = raw.upper()
    return upper if upper in SEVERITIES else "INDETERMINATE"
