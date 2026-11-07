"""Moteur d'états.

Partie pure (sans base, testée seule) :
  map_raw_status → element_status → alarm_effects → consolidate_site → debounce

Partie orchestration : ``evaluate_sites()`` lit la base, applique les fonctions pures,
écrit les états et historise toutes les transitions.

Principe non négociable : une perte de collecte (source en échec, données périmées)
donne UNKNOWN, jamais DOWN.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

UP, DOWN, DEGRADED, UNKNOWN, UNSUPERVISED = "UP", "DOWN", "DEGRADED", "UNKNOWN", "UNSUPERVISED"
ELEMENT_STATUSES = (UP, DOWN, DEGRADED, UNKNOWN)
MAJOR_SEVERITIES = ("CRITICAL", "MAJOR")
UNSUPERVISED_MESSAGE = "Non supervisé : aucun OMC ne remonte ce site"


# ---------------------------------------------------------------------------
# Paramètres
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StatusRules:
    partial_down_is_degraded: bool = True
    major_alarm_degrades: bool = True
    unknown_elements_policy: str = "ignore"  # ignore | degrade
    down_confirm_s: int = 0
    up_confirm_s: int = 0
    default_stale_after_s: int = 1800

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> StatusRules:
        known = {k: v for k, v in (values or {}).items() if k in cls.__dataclass_fields__}
        return cls(**known)


# ---------------------------------------------------------------------------
# Fonctions pures
# ---------------------------------------------------------------------------


def map_raw_status(raw: str | None, status_map: Mapping[str, str] | None) -> tuple[str, str | None]:
    """Traduit une valeur brute OMC via ``value_maps.status``.

    Renvoie (état, avertissement). Valeur absente ou inconnue : UNKNOWN (+ avertissement si inconnue).
    """
    if raw is None or str(raw).strip() == "":
        return UNKNOWN, None
    value = str(raw).strip()
    status_map = status_map or {}
    mapped = status_map.get(value)
    if mapped is None:
        lowered = value.lower()
        mapped = next((v for k, v in status_map.items() if str(k).lower() == lowered), None)
    if mapped is None:
        return UNKNOWN, f"Valeur d'état non traduite : {value!r}"
    mapped = str(mapped).upper()
    if mapped not in ELEMENT_STATUSES:
        return UNKNOWN, f"Traduction invalide pour {value!r} : {mapped!r}"
    return mapped, None


def is_stale(observed_at: datetime | None, now: datetime, stale_after_s: int) -> bool:
    return observed_at is None or (now - observed_at) > timedelta(seconds=stale_after_s)


def element_status(
    mapped: str,
    observed_at: datetime | None,
    now: datetime,
    stale_after_s: int,
    *,
    source_failed: bool = False,
    forced: str | None = None,
) -> str:
    """État effectif d'un élément.

    Collecte en échec ou observation périmée : UNKNOWN (jamais DOWN), quelles que soient les alarmes.
    Sinon une règle d'alarme validée peut forcer DOWN, ou DEGRADED si l'élément est UP.
    """
    if source_failed or is_stale(observed_at, now, stale_after_s):
        return UNKNOWN
    if forced == DOWN:
        return DOWN
    if forced == DEGRADED and mapped == UP:
        return DEGRADED
    return mapped


@dataclass(frozen=True)
class AlarmView:
    id: int
    site_id: int | None
    element_id: int | None
    source_id: int | None
    vendor: str | None
    code: str | None
    severity: str
    description: str | None


@dataclass(frozen=True)
class RuleView:
    id: int
    source_id: int | None
    vendor: str | None
    match_code: str | None
    match_pattern: str | None
    effect: str
    scope: str


def rule_matches(rule: RuleView, alarm: AlarmView) -> bool:
    if rule.source_id is not None and rule.source_id != alarm.source_id:
        return False
    if rule.vendor and (alarm.vendor or "").upper() != rule.vendor.upper():
        return False
    if rule.match_code and (alarm.code or "").strip().upper() == rule.match_code.strip().upper():
        return True
    if rule.match_pattern:
        try:
            return re.search(rule.match_pattern, f"{alarm.code or ''} {alarm.description or ''}", re.I) is not None
        except re.error:
            return False
    return False


def _stronger(current: str | None, new: str) -> str:
    return DOWN if DOWN in (current, new) else new


def alarm_effects(
    alarms: Iterable[AlarmView], rules: Sequence[RuleView]
) -> tuple[dict[int, str], dict[int, str]]:
    """Effets des règles d'alarmes (déjà filtrées : validées et actives).

    Renvoie (forçages par site, forçages par élément). DOWN l'emporte sur DEGRADED.
    """
    by_site: dict[int, str] = {}
    by_element: dict[int, str] = {}
    for alarm in alarms:
        for rule in rules:
            if not rule_matches(rule, alarm):
                continue
            if rule.scope == "ELEMENT" and alarm.element_id is not None:
                by_element[alarm.element_id] = _stronger(by_element.get(alarm.element_id), rule.effect)
            elif alarm.site_id is not None:
                by_site[alarm.site_id] = _stronger(by_site.get(alarm.site_id), rule.effect)
    return by_site, by_element


def consolidate_site(
    statuses: Sequence[str],
    alarm_severities: Iterable[str],
    rules: StatusRules,
    forced: str | None = None,
) -> tuple[str, str]:
    """État consolidé d'un site à partir de ses éléments. Renvoie (état, motif)."""
    total = len(statuses)
    known = [s for s in statuses if s != UNKNOWN]
    if not known:
        return UNKNOWN, "aucun état connu" if total else "aucun élément"
    unknown_count = total - len(known)
    degrade_unknown = unknown_count > 0 and rules.unknown_elements_policy == "degrade"
    downs = sum(1 for s in known if s == DOWN)
    degraded = sum(1 for s in known if s == DEGRADED)

    if forced == DOWN:
        return DOWN, "règle d'alarme (DOWN)"
    if downs == len(known):
        if degrade_unknown:
            return DEGRADED, f"{downs} élément(s) DOWN, {unknown_count} inconnu(s)"
        return DOWN, f"{downs}/{len(known)} élément(s) DOWN"
    if downs or degraded:
        if degraded or rules.partial_down_is_degraded:
            return DEGRADED, f"{downs} DOWN, {degraded} dégradé(s) sur {total}"
    if forced == DEGRADED:
        return DEGRADED, "règle d'alarme (DEGRADED)"
    if rules.major_alarm_degrades and any(s in MAJOR_SEVERITIES for s in alarm_severities):
        return DEGRADED, "alarme critique ou majeure active"
    if degrade_unknown:
        return DEGRADED, f"{unknown_count} élément(s) inconnu(s)"
    return UP, f"{len(known)}/{total} élément(s) opérationnel(s)"


@dataclass(frozen=True)
class Debounced:
    status: str
    since: datetime | None
    pending: str | None
    pending_since: datetime | None
    changed: bool


def debounce(
    current: str,
    current_since: datetime | None,
    pending: str | None,
    pending_since: datetime | None,
    candidate: str,
    detected_at: datetime,
    now: datetime,
    rules: StatusRules,
) -> Debounced:
    """Anti-rebond : DOWN confirmé après ``down_confirm_s``, UP après ``up_confirm_s``.

    La transition est horodatée à la première détection (``pending_since``).
    """
    if candidate == current:
        return Debounced(current, current_since, None, None, False)
    first_seen = pending_since if pending == candidate and pending_since else detected_at
    delay = rules.down_confirm_s if candidate == DOWN else rules.up_confirm_s if candidate == UP else 0
    # Les transitions vers UNKNOWN (perte de collecte) ne sont jamais retardées.
    if candidate == UNKNOWN or delay <= 0 or (now - first_seen) >= timedelta(seconds=delay):
        return Debounced(candidate, first_seen, None, None, True)
    return Debounced(current, current_since, candidate, first_seen, False)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class EvaluationStats:
    sites: int = 0
    elements: int = 0
    site_transitions: int = 0
    element_transitions: int = 0
    unmapped: int = 0
    warnings: list[str] = field(default_factory=list)


def _id_filter(column: str, site_ids: Sequence[int] | None) -> tuple[str, dict]:
    if site_ids is None:
        return "TRUE", {}
    return f"{column} = ANY(:site_ids)", {"site_ids": list(site_ids)}


def evaluate_sites(
    session: Session, site_ids: Iterable[int] | None = None, now: datetime | None = None
) -> EvaluationStats:
    """Recalcule l'état des éléments et des sites (tous si ``site_ids`` vaut None)."""
    from .settings_service import get_status_rules

    now = now or datetime.now(UTC)
    ids = None if site_ids is None else sorted(set(site_ids))
    stats = EvaluationStats()
    if ids is not None and not ids:
        return stats
    rules = get_status_rules(session)

    where_e, params = _id_filter("e.site_id", ids)
    elements = session.execute(
        text(
            f"""
            SELECT e.id, e.site_id, e.source_id, e.raw_status, e.observed_at, e.oper_status,
                   src.value_maps, src.stale_after_s, src.last_status
              FROM site_elements e
              LEFT JOIN omc_sources src ON src.id = e.source_id
             WHERE e.active AND {where_e}
            """
        ),
        params,
    ).all()
    where_a, _ = _id_filter("a.site_id", ids)
    alarms = [
        AlarmView(r.id, r.site_id, r.element_id, r.source_id, r.vendor, r.code, r.severity, r.description)
        for r in session.execute(
            text(
                f"""
                SELECT a.id, a.site_id, a.element_id, a.source_id, src.vendor, a.code, a.severity, a.description
                  FROM alarms a
                  LEFT JOIN omc_sources src ON src.id = a.source_id
                 WHERE a.is_active AND a.site_id IS NOT NULL AND {where_a}
                   AND COALESCE(src.last_status, 'OK') <> 'FAILED'
                """
            ),
            params,
        )
    ]
    rules_rows = [
        RuleView(r.id, r.source_id, r.vendor, r.match_code, r.match_pattern, r.effect, r.scope)
        for r in session.execute(
            text(
                "SELECT id, source_id, vendor, match_code, match_pattern, effect, scope "
                "FROM alarm_rules WHERE validated AND enabled"
            )
        )
    ]
    site_forced, element_forced = alarm_effects(alarms, rules_rows)
    severities: dict[int, list[str]] = defaultdict(list)
    for alarm in alarms:
        severities[alarm.site_id].append(alarm.severity)

    # Éléments --------------------------------------------------------------
    per_site: dict[int, list[str]] = defaultdict(list)
    detected: dict[int, datetime] = {}
    element_updates, history = [], []
    for e in elements:
        mapped, warning = map_raw_status(e.raw_status, (e.value_maps or {}).get("status"))
        if warning:
            stats.unmapped += 1
            if len(stats.warnings) < 50:
                stats.warnings.append(f"NE {e.id} : {warning}")
        status = element_status(
            mapped,
            e.observed_at,
            now,
            e.stale_after_s or rules.default_stale_after_s,
            source_failed=e.last_status == "FAILED",
            forced=element_forced.get(e.id),
        )
        per_site[e.site_id].append(status)
        if e.observed_at and status != UNKNOWN:
            detected[e.site_id] = max(detected.get(e.site_id, e.observed_at), e.observed_at)
        if status != e.oper_status:
            changed_at = e.observed_at if (status != UNKNOWN and e.observed_at) else now
            element_updates.append({"id": e.id, "status": status, "since": changed_at})
            history.append(
                {"site_id": e.site_id, "element_id": e.id, "old": e.oper_status, "new": status,
                 "at": changed_at, "source_id": e.source_id, "reason": warning or "état OMC"}
            )
    stats.elements = len(elements)
    stats.element_transitions = len(element_updates)

    # Sites ---------------------------------------------------------------------
    where_s, _ = _id_filter("id", ids)
    sites = session.execute(
        text(
            f"""
            SELECT id, display_status, status_since, pending_status, pending_since, in_reference, is_supervised
              FROM sites WHERE active AND {where_s}
            """
        ),
        params,
    ).all()
    site_updates = []
    for s in sites:
        if s.in_reference and not s.is_supervised:
            reason = UNSUPERVISED_MESSAGE
            if s.display_status == UNSUPERVISED:
                decision = Debounced(UNSUPERVISED, s.status_since, None, None, False)
            else:
                decision = Debounced(UNSUPERVISED, now, None, None, True)
        else:
            candidate, reason = consolidate_site(
                per_site.get(s.id, []), severities.get(s.id, []), rules, site_forced.get(s.id)
            )
            current = UNKNOWN if s.display_status == UNSUPERVISED else s.display_status
            decision = debounce(
                current, s.status_since, s.pending_status, s.pending_since,
                candidate, detected.get(s.id, now), now, rules,
            )
        if decision.changed or decision.pending != s.pending_status or decision.pending_since != s.pending_since:
            site_updates.append(
                {"id": s.id, "status": decision.status, "since": decision.since,
                 "pending": decision.pending, "pending_since": decision.pending_since}
            )
        if decision.changed:
            stats.site_transitions += 1
            history.append(
                {"site_id": s.id, "element_id": None, "old": s.display_status, "new": decision.status,
                 "at": decision.since or now, "source_id": None, "reason": reason}
            )
    stats.sites = len(sites)

    if element_updates:
        session.execute(
            text("UPDATE site_elements SET oper_status = :status, status_since = :since, updated_at = now() WHERE id = :id"),
            element_updates,
        )
    if site_updates:
        session.execute(
            text(
                "UPDATE sites SET display_status = :status, status_since = :since, pending_status = :pending, "
                "pending_since = :pending_since, updated_at = now() WHERE id = :id"
            ),
            site_updates,
        )
    if history:
        session.execute(
            text(
                "INSERT INTO status_history (site_id, element_id, old_status, new_status, changed_at, source_id, reason) "
                "VALUES (:site_id, :element_id, :old, :new, :at, :source_id, :reason)"
            ),
            history,
        )
    return stats
