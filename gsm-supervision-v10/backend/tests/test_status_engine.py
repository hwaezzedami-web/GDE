"""Tests unitaires du moteur d'états (fonctions pures)."""
from datetime import datetime, timedelta, timezone

from app.services.status_engine import (
    AlarmInput,
    ElementInput,
    RuleInput,
    compute_site_status,
    decide_transition,
)

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
RULES = {"default_stale_after_s": 1800, "down_confirm_s": 0, "up_confirm_s": 0,
         "unknown_elements_policy": "ignore", "major_alarm_degrades": True, "partial_down_is_degraded": True}


def el(i, tech, status, age_s=10, stale=600, vendor="HUAWEI"):
    return ElementInput(i, tech, status, NOW - timedelta(seconds=age_s) if age_s is not None else None,
                        stale, "SRC", vendor)


def test_all_up():
    r = compute_site_status([el(1, "2G", "UP"), el(2, "4G", "UP")], [], [], RULES, NOW)
    assert r.status == "UP" and r.technologies == ["2G", "4G"] and not r.is_stale


def test_all_down():
    r = compute_site_status([el(1, "2G", "DOWN"), el(2, "4G", "DOWN")], [], [], RULES, NOW)
    assert r.status == "DOWN"
    assert "2G" in r.reason and "4G" in r.reason


def test_partial_down_is_degraded():
    r = compute_site_status([el(1, "2G", "UP"), el(2, "4G", "DOWN")], [], [], RULES, NOW)
    assert r.status == "DEGRADED"
    r2 = compute_site_status([el(1, "2G", "UP"), el(2, "4G", "DOWN")], [], [],
                             {**RULES, "partial_down_is_degraded": False}, NOW)
    assert r2.status == "UP"


def test_stale_data_gives_unknown_never_down():
    """Perte de collecte : les données vieillissent -> UNKNOWN, jamais DOWN."""
    r = compute_site_status([el(1, "2G", "UP", age_s=4000), el(2, "4G", "UP", age_s=4000)], [], [], RULES, NOW)
    assert r.status == "UNKNOWN" and r.is_stale
    r = compute_site_status([el(1, "2G", "DOWN", age_s=4000)], [], [], RULES, NOW)
    assert r.status == "UNKNOWN"


def test_never_stale_for_manual_sources():
    r = compute_site_status([el(1, "2G", "UP", age_s=10 ** 7, stale=None)], [], [], RULES, NOW)
    assert r.status == "UP"


def test_unknown_policy():
    els = [el(1, "2G", "UP"), el(2, "4G", "UP", age_s=4000)]
    assert compute_site_status(els, [], [], RULES, NOW).status == "UP"
    assert compute_site_status(els, [], [], {**RULES, "unknown_elements_policy": "degrade"}, NOW).status == "DEGRADED"


def test_no_elements():
    assert compute_site_status([], [], [], RULES, NOW).status == "UNKNOWN"


def test_alarm_rules_need_match_and_apply_effect():
    els = [el(1, "2G", "UP"), el(2, "4G", "UP")]
    alarm = AlarmInput(10, 2, "LNK-1", "Cell out of service", "MINOR", "HUAWEI")
    rule = RuleInput(1, "HUAWEI", "LNK-1", None, "DOWN", "ELEMENT")
    r = compute_site_status(els, [alarm], [rule], RULES, NOW)
    assert r.status == "DEGRADED" and r.alarm_id == 10
    site_rule = RuleInput(2, "HUAWEI", None, r"out of service", "DOWN", "SITE")
    assert compute_site_status(els, [alarm], [site_rule], RULES, NOW).status == "DOWN"
    other_vendor = RuleInput(3, "ZTE", "LNK-1", None, "DOWN", "SITE")
    assert compute_site_status(els, [alarm], [other_vendor], RULES, NOW).status == "UP"


def test_major_alarm_degrades_up_site():
    els = [el(1, "2G", "UP")]
    a = AlarmInput(5, None, "PWR", "Mains failure", "MAJOR", "HUAWEI")
    assert compute_site_status(els, [a], [], RULES, NOW).status == "DEGRADED"
    assert compute_site_status(els, [a], [], {**RULES, "major_alarm_degrades": False}, NOW).status == "UP"
    minor = AlarmInput(6, None, "X", "minor", "MINOR", "HUAWEI")
    assert compute_site_status(els, [minor], [], RULES, NOW).status == "UP"


def test_vendor_multi():
    r = compute_site_status([el(1, "2G", "UP", vendor="HUAWEI"), el(2, "4G", "UP", vendor="ZTE")], [], [], RULES, NOW)
    assert r.vendor == "MULTI"


def test_debounce_down_confirmation():
    s = {**RULES, "down_confirm_s": 300}
    # 1re détection : en attente
    new, pend, since, _ = decide_transition("UP", None, None, "DOWN", s, NOW)
    assert new is None and pend == "DOWN" and since == NOW
    # 2 min plus tard : toujours en attente
    new, pend, since2, _ = decide_transition("UP", pend, since, "DOWN", s, NOW + timedelta(minutes=2))
    assert new is None and since2 == NOW
    # 5 min plus tard : confirmé, horodaté à la 1re détection
    new, pend, _, changed = decide_transition("UP", "DOWN", NOW, "DOWN", s, NOW + timedelta(minutes=5))
    assert new == "DOWN" and pend is None and changed == NOW
    # retour UP avant confirmation : l'attente est annulée
    new, pend, since, _ = decide_transition("UP", "DOWN", NOW, "UP", s, NOW + timedelta(minutes=1))
    assert new is None and pend is None and since is None
