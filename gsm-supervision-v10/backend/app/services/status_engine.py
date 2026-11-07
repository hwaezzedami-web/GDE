"""Moteur d'états des sites (UP / DOWN / DEGRADED / UNKNOWN).

Principes (détaillés dans docs/03_REGLES_ETATS.md) :

1. L'état d'un équipement vient de la source OMC (site_elements.oper_status).
   Si sa dernière observation est plus ancienne que le seuil de péremption de
   sa source, son état effectif devient UNKNOWN : une coupure de la collecte
   n'est JAMAIS interprétée comme une panne radio.
2. Les alarmes actives ne modifient l'état que si elles correspondent à une
   règle activée ET validée par un administrateur (table alarm_rules).
3. L'état du site est consolidé à partir de ses équipements :
     - aucun équipement à l'état connu           -> UNKNOWN
     - tous les équipements connus DOWN          -> DOWN
     - au moins un équipement DOWN ou DEGRADED   -> DEGRADED (paramétrable)
     - sinon                                     -> UP
     - alarme CRITICAL/MAJOR active sur site UP  -> DEGRADED (paramétrable)
4. Anti-rebond : un nouvel état DOWN (resp. UP) n'est confirmé qu'après avoir
   persisté down_confirm_s (resp. up_confirm_s) secondes.
5. Chaque transition d'état du site est enregistrée dans status_history.

Le moteur est une fonction pure (compute_site_status) + une fonction
d'orchestration en base (evaluate_sites), pour faciliter les tests.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from .settings_service import get_setting

log = logging.getLogger(__name__)

RANK = {"UP": 0, "DEGRADED": 1, "DOWN": 2}
EVAL_LOCK = (7_421_001, 0)   # verrou consultatif partagé collecteur / API
MAJOR_SEVERITIES = ("CRITICAL", "MAJOR")


@dataclass
class ElementInput:
    id: int
    technology: str
    oper_status: str
    observed_at: datetime | None
    stale_after_s: int | None          # None = jamais périmé
    source_code: str
    vendor: str


@dataclass
class AlarmInput:
    id: int
    element_id: int | None
    alarm_code: str | None
    description: str | None
    severity: str
    vendor: str


@dataclass
class RuleInput:
    id: int
    vendor: str
    alarm_code: str | None
    text_pattern: str | None
    effect: str
    scope: str
    _rx: re.Pattern | None = field(default=None, repr=False)

    def matches(self, a: AlarmInput) -> bool:
        if a.vendor != self.vendor:
            return False
        if self.alarm_code and (a.alarm_code or "").strip() == self.alarm_code.strip():
            return True
        if self.text_pattern:
            if self._rx is None:
                try:
                    self._rx = re.compile(self.text_pattern, re.IGNORECASE)
                except re.error:
                    log.warning("Règle d'alarme %s : expression régulière invalide", self.id)
                    return False
            return bool(self._rx.search(a.description or ""))
        return False


@dataclass
class SiteResult:
    status: str
    reason: str
    is_stale: bool
    last_observed_at: datetime | None
    technologies: list[str]
    vendor: str | None
    alarm_id: int | None = None


def _fmt(dt: datetime | None) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if dt else "jamais"


def compute_site_status(
    elements: list[ElementInput],
    alarms: list[AlarmInput],
    rules: list[RuleInput],
    settings: dict,
    now: datetime,
) -> SiteResult:
    techs = sorted({e.technology for e in elements})
    vendors = {e.vendor for e in elements}
    vendor = vendors.pop() if len(vendors) == 1 else ("MULTI" if vendors else None)
    last_obs = max((e.observed_at for e in elements if e.observed_at), default=None)

    if not elements:
        return SiteResult("UNKNOWN", "Aucun équipement actif connu pour ce site", False, None, techs, vendor)

    # --- Effets des alarmes validées -------------------------------------
    element_effect: dict[int, tuple[str, AlarmInput]] = {}
    site_effect: tuple[str, AlarmInput] | None = None
    for a in alarms:
        for r in rules:
            if not r.matches(a):
                continue
            if r.scope == "SITE" or a.element_id is None:
                if site_effect is None or RANK[r.effect] > RANK[site_effect[0]]:
                    site_effect = (r.effect, a)
            else:
                cur = element_effect.get(a.element_id)
                if cur is None or RANK[r.effect] > RANK[cur[0]]:
                    element_effect[a.element_id] = (r.effect, a)

    # --- État effectif de chaque équipement ------------------------------
    effective: dict[str, list[str]] = {"UP": [], "DOWN": [], "DEGRADED": [], "UNKNOWN": []}
    stale_any = False
    alarm_used: AlarmInput | None = None
    for e in elements:
        st = e.oper_status
        if e.observed_at is None:
            st = "UNKNOWN"
        elif e.stale_after_s is not None and (now - e.observed_at).total_seconds() > e.stale_after_s:
            st = "UNKNOWN"
            stale_any = True
        if st != "UNKNOWN" and e.id in element_effect:
            eff, a = element_effect[e.id]
            if RANK[eff] > RANK.get(st, 0):
                st = eff
                alarm_used = a
        effective[st].append(e.technology)

    known = len(elements) - len(effective["UNKNOWN"])
    alarm_id = None
    if known == 0:
        if stale_any:
            reason = f"Données périmées : dernière observation {_fmt(last_obs)}"
        else:
            reason = "Aucune information d'état fiable reçue de la source"
        status = "UNKNOWN"
    elif len(effective["DOWN"]) == known:
        status = "DOWN"
        reason = "Panne : " + ", ".join(sorted(set(effective["DOWN"]))) + " hors service"
    elif effective["DOWN"] or effective["DEGRADED"]:
        if settings.get("partial_down_is_degraded", True):
            status = "DEGRADED"
            parts = []
            if effective["DOWN"]:
                parts.append(", ".join(sorted(set(effective["DOWN"]))) + " hors service")
            if effective["DEGRADED"]:
                parts.append(", ".join(sorted(set(effective["DEGRADED"]))) + " dégradé")
            reason = "Partiel : " + " ; ".join(parts)
        else:
            status, reason = "UP", "Au moins une technologie opérationnelle"
    else:
        status, reason = "UP", "Opérationnel (confirmé par la source)"

    if alarm_used and status in ("DOWN", "DEGRADED"):
        reason += f" — règle d'alarme : {alarm_used.alarm_code or ''} {alarm_used.description or ''}".rstrip()
        alarm_id = alarm_used.id

    if status != "UNKNOWN":
        if (status == "UP" and effective["UNKNOWN"]
                and settings.get("unknown_elements_policy") == "degrade"):
            status = "DEGRADED"
            reason = "État inconnu pour : " + ", ".join(sorted(set(effective["UNKNOWN"])))
        if site_effect and RANK[site_effect[0]] > RANK[status]:
            status = site_effect[0]
            a = site_effect[1]
            reason = f"Règle d'alarme site : {a.alarm_code or ''} {a.description or ''}".strip()
            alarm_id = a.id
        if status == "UP" and settings.get("major_alarm_degrades", True):
            major = [a for a in alarms if a.severity in MAJOR_SEVERITIES]
            if major:
                a = sorted(major, key=lambda x: MAJOR_SEVERITIES.index(x.severity))[0]
                status = "DEGRADED"
                reason = f"Alarme {a.severity.lower()} active : {a.alarm_code or ''} {a.description or ''}".strip()
                alarm_id = a.id

    return SiteResult(status, reason, stale_any, last_obs, techs, vendor, alarm_id)


def decide_transition(current: str, pending: str | None, pending_since: datetime | None,
                      candidate: str, settings: dict, now: datetime
                      ) -> tuple[str | None, str | None, datetime | None, datetime | None]:
    """Applique l'anti-rebond.

    Retourne (nouvel_état ou None si pas de transition, pending_status, pending_since, changed_at)
    """
    if candidate == current:
        return None, None, None, None
    if candidate == "DOWN":
        delay = int(settings.get("down_confirm_s", 0))
    elif candidate == "UP":
        delay = int(settings.get("up_confirm_s", 0))
    else:
        delay = 0
    if delay <= 0:
        return candidate, None, None, now
    if pending == candidate and pending_since is not None:
        if (now - pending_since).total_seconds() >= delay:
            return candidate, None, None, pending_since
        return None, pending, pending_since, None
    return None, candidate, now, None


# ---------------------------------------------------------------------------
# Orchestration en base
# ---------------------------------------------------------------------------

def _load_rules(db: Session) -> list[RuleInput]:
    rows = db.execute(text("""
        SELECT id, vendor, alarm_code, text_pattern, effect, scope
        FROM alarm_rules WHERE enabled AND validated_at IS NOT NULL
    """)).all()
    return [RuleInput(*r) for r in rows]


def evaluate_sites(db: Session, site_ids: Iterable[int] | None = None,
                   now: datetime | None = None) -> dict:
    """Recalcule l'état des sites (tous, ou la liste donnée) et historise les transitions.

    N'effectue pas de commit : l'appelant valide la transaction. Un verrou
    transactionnel sérialise les réévaluations concurrentes (collecteur, API)
    pour qu'une même transition ne soit jamais historisée deux fois.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(:a, :b)"), {"a": EVAL_LOCK[0], "b": EVAL_LOCK[1]})
    now = now or datetime.now(timezone.utc)
    settings = get_setting(db, "status_rules")
    default_stale = int(settings.get("default_stale_after_s", 1800))
    rules = _load_rules(db)

    params: dict = {"dstale": default_stale}
    site_filter = ""
    if site_ids is not None:
        ids = list(set(site_ids))
        if not ids:
            return {"evaluated": 0, "transitions": 0}
        params["ids"] = ids
        site_filter = "AND s.id = ANY(:ids)"

    sites = db.execute(text(f"""
        SELECT s.id, s.status, s.pending_status, s.pending_since, s.status_reason,
               s.is_stale, s.last_observed_at, s.technologies, s.vendor,
               s.in_reference, s.ref_technologies, s.is_supervised, s.last_supervised_at
        FROM sites s WHERE s.is_active {site_filter}
    """), params).all()

    elems: dict[int, list[ElementInput]] = {}
    for r in db.execute(text(f"""
        SELECT e.site_id, e.id, e.technology, e.oper_status, e.status_observed_at,
               CASE WHEN o.stale_after_s IS NOT NULL THEN o.stale_after_s
                    WHEN o.connector_type = 'manual_csv' THEN NULL
                    ELSE :dstale END AS stale_after,
               o.code, o.vendor
        FROM site_elements e JOIN omc_sources o ON o.id = e.omc_source_id
        JOIN sites s ON s.id = e.site_id
        WHERE e.is_active AND s.is_active {site_filter}
    """), params):
        elems.setdefault(r[0], []).append(ElementInput(*r[1:]))

    alarms: dict[int, list[AlarmInput]] = {}
    for r in db.execute(text(f"""
        SELECT a.site_id, a.id, a.element_id, a.alarm_code, a.description, a.severity, o.vendor
        FROM alarms a JOIN omc_sources o ON o.id = a.omc_source_id
        JOIN sites s ON s.id = a.site_id
        WHERE a.state = 'ACTIVE' AND s.is_active {site_filter}
    """), params):
        alarms.setdefault(r[0], []).append(AlarmInput(*r[1:]))

    updates, history = [], []
    transitions = 0
    for (sid, cur, pend, pend_since, cur_reason, cur_stale, cur_obs, cur_techs, cur_vendor,
         in_ref, ref_techs, cur_sup, cur_sup_at) in sites:
        site_elems = elems.get(sid, [])
        res = compute_site_status(site_elems, alarms.get(sid, []), rules, settings, now)
        supervised = bool(site_elems)
        sup_at = cur_sup_at
        if res.last_observed_at and (sup_at is None or res.last_observed_at > sup_at):
            sup_at = res.last_observed_at
        if not supervised and in_ref:
            # Site du référentiel qu'aucun OMC ne remonte : ce n'est pas une panne, l'état reste inconnu
            res.reason = "Non supervisé : aucun OMC ne remonte ce site"
            res.technologies = sorted(ref_techs or [])
        new_status, new_pend, new_pend_since, changed_at = decide_transition(
            cur, pend, pend_since, res.status, settings, now)
        row = {
            "id": sid,
            "pending_status": new_pend,
            "pending_since": new_pend_since,
            "is_stale": res.is_stale,
            "last_observed_at": res.last_observed_at,
            "technologies": res.technologies,
            "vendor": res.vendor or cur_vendor,
            "is_supervised": supervised,
            "last_supervised_at": sup_at,
        }
        if new_status is not None:
            transitions += 1
            row.update(status=new_status, status_since=changed_at, status_reason=res.reason)
            history.append({
                "site_id": sid, "old": cur, "new": new_status, "changed_at": changed_at,
                "observed_at": res.last_observed_at, "reason": res.reason, "alarm_id": res.alarm_id,
            })
        else:
            row.update(status=cur, status_since=None,
                       status_reason=res.reason if res.status == cur else cur_reason)
        changed = (new_status is not None or new_pend != pend or new_pend_since != pend_since
                   or res.is_stale != cur_stale or res.last_observed_at != cur_obs
                   or res.technologies != list(cur_techs or []) or row["vendor"] != cur_vendor
                   or row["status_reason"] != cur_reason
                   or supervised != cur_sup or sup_at != cur_sup_at)
        if changed:
            updates.append(row)

    if updates:
        db.execute(text("""
            UPDATE sites SET
                status = :status,
                status_since = COALESCE(:status_since, status_since),
                status_reason = :status_reason,
                pending_status = :pending_status,
                pending_since = :pending_since,
                is_stale = :is_stale,
                last_observed_at = :last_observed_at,
                technologies = :technologies,
                vendor = :vendor,
                is_supervised = :is_supervised,
                last_supervised_at = :last_supervised_at,
                updated_at = now()
            WHERE id = :id
        """), updates)
    if history:
        db.execute(text("""
            INSERT INTO status_history (entity_type, site_id, old_status, new_status,
                                        changed_at, observed_at, source, reason, alarm_id)
            VALUES ('SITE', :site_id, :old, :new, :changed_at, :observed_at, 'ENGINE', :reason, :alarm_id)
        """), history)
    return {"evaluated": len(sites), "transitions": transitions, "updated": len(updates)}


def evaluate_all_locked() -> dict | None:
    """Réévaluation complète, exécutée par un seul processus à la fois.

    Appelée périodiquement par le service de collecte ET par l'API (filet de
    sécurité) : si le collecteur est arrêté, les données continuent de vieillir
    et les sites passent UNKNOWN au lieu de rester affichés avec un état figé.
    Retourne None si un autre processus effectue déjà la réévaluation.
    """
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        got = db.execute(text("SELECT pg_try_advisory_xact_lock(:a, :b)"),
                         {"a": EVAL_LOCK[0], "b": EVAL_LOCK[1]}).scalar()
        if not got:
            db.rollback()
            return None
        res = evaluate_sites(db)
        db.commit()
        return res
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
