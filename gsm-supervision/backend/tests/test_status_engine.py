"""Moteur d'états : fonctions pures (sans base de données)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.status_engine import (
    DEGRADED,
    DOWN,
    UNKNOWN,
    UP,
    AlarmView,
    RuleView,
    StatusRules,
    alarm_effects,
    consolidate_site,
    debounce,
    element_status,
    map_raw_status,
)

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
STATUS_MAP = {"1": "UP", "0": "DOWN", "2": "DEGRADED"}


# --- Traduction des valeurs brutes -------------------------------------------


def test_known_raw_value_is_translated():
    assert map_raw_status("1", STATUS_MAP) == (UP, None)
    assert map_raw_status(" 0 ", STATUS_MAP) == (DOWN, None)


def test_unknown_raw_value_gives_unknown_with_warning():
    status, warning = map_raw_status("77", STATUS_MAP)
    assert status == UNKNOWN
    assert warning and "77" in warning


def test_missing_raw_value_is_unknown_without_warning():
    assert map_raw_status(None, STATUS_MAP) == (UNKNOWN, None)


# --- Élément : péremption et collecte en échec -----------------------------------


def test_stale_observation_is_unknown_even_if_down():
    observed = NOW - timedelta(seconds=1801)
    assert element_status(DOWN, observed, NOW, 1800) == UNKNOWN


def test_fresh_observation_keeps_status():
    observed = NOW - timedelta(seconds=60)
    assert element_status(DOWN, observed, NOW, 1800) == DOWN


def test_failed_source_is_unknown_not_down():
    """Règle non négociable : perte de collecte ≠ panne radio."""
    observed = NOW - timedelta(seconds=10)
    assert element_status(DOWN, observed, NOW, 1800, source_failed=True) == UNKNOWN


def test_missing_observation_time_is_unknown():
    assert element_status(UP, None, NOW, 1800) == UNKNOWN


def test_validated_alarm_rule_can_force_down_and_degrade():
    observed = NOW - timedelta(seconds=10)
    assert element_status(UP, observed, NOW, 1800, forced=DOWN) == DOWN
    assert element_status(UP, observed, NOW, 1800, forced=DEGRADED) == DEGRADED
    assert element_status(DOWN, observed, NOW, 1800, forced=DEGRADED) == DOWN


# --- Règles d'alarmes ---------------------------------------------------------------


def test_rule_match_by_code_and_source():
    rule = RuleView(1, source_id=5, vendor=None, match_code="NODEB_UNAVAILABLE", match_pattern=None,
                    effect=DOWN, scope="SITE")
    alarm = AlarmView(10, site_id=1, element_id=None, source_id=5, vendor="HUAWEI",
                      code="nodeb_unavailable", severity="MAJOR", description=None)
    other_source = AlarmView(11, site_id=1, element_id=None, source_id=6, vendor="HUAWEI",
                             code="NODEB_UNAVAILABLE", severity="MAJOR", description=None)
    by_site, _ = alarm_effects([alarm, other_source], [rule])
    assert by_site == {1: DOWN}


def test_rule_match_by_pattern_on_description():
    rule = RuleView(2, None, None, None, r"OML.*Fault", DEGRADED, "SITE")
    alarm = AlarmView(12, 3, None, 5, None, "X1", "MINOR", "OML Fault on board")
    by_site, _ = alarm_effects([alarm], [rule])
    assert by_site == {3: DEGRADED}


def test_invalid_pattern_never_matches():
    rule = RuleView(3, None, None, None, "([", DOWN, "SITE")
    alarm = AlarmView(13, 3, None, 5, None, "X", "MAJOR", "([")
    assert alarm_effects([alarm], [rule]) == ({}, {})


def test_element_scope_rule_targets_element_not_site():
    rule = RuleView(4, None, None, "CELL_DOWN", None, DOWN, "ELEMENT")
    alarm = AlarmView(14, 7, 70, 5, None, "CELL_DOWN", "CRITICAL", None)
    by_site, by_element = alarm_effects([alarm], [rule])
    assert by_site == {}
    assert by_element == {70: DOWN}


def test_down_wins_over_degraded_for_same_site():
    rules = [
        RuleView(5, None, None, "A", None, DEGRADED, "SITE"),
        RuleView(6, None, None, "B", None, DOWN, "SITE"),
    ]
    alarms = [
        AlarmView(15, 8, None, 5, None, "A", "MINOR", None),
        AlarmView(16, 8, None, 5, None, "B", "MAJOR", None),
    ]
    assert alarm_effects(alarms, rules)[0] == {8: DOWN}


# --- Consolidation par site ----------------------------------------------------------


RULES = StatusRules()


def test_all_up_is_up():
    assert consolidate_site([UP, UP], [], RULES)[0] == UP


def test_all_down_is_down():
    assert consolidate_site([DOWN, DOWN], [], RULES)[0] == DOWN


def test_partial_down_is_degraded_by_default():
    assert consolidate_site([UP, DOWN], [], RULES)[0] == DEGRADED


def test_partial_down_stays_up_when_parameter_disabled():
    rules = StatusRules(partial_down_is_degraded=False)
    assert consolidate_site([UP, DOWN], [], rules)[0] == UP


def test_major_alarm_degrades_an_all_up_site():
    assert consolidate_site([UP, UP], ["MAJOR"], RULES)[0] == DEGRADED


def test_major_alarm_ignored_when_parameter_disabled():
    rules = StatusRules(major_alarm_degrades=False)
    assert consolidate_site([UP], ["CRITICAL"], rules)[0] == UP


def test_no_known_state_is_unknown():
    assert consolidate_site([UNKNOWN, UNKNOWN], [], RULES)[0] == UNKNOWN


def test_unknown_elements_ignored_by_default():
    assert consolidate_site([UP, UNKNOWN], [], RULES)[0] == UP


def test_unknown_elements_degrade_when_policy_says_so():
    rules = StatusRules(unknown_elements_policy="degrade")
    assert consolidate_site([UP, UNKNOWN], [], rules)[0] == DEGRADED


def test_forced_down_rule_wins_over_everything():
    assert consolidate_site([UP, UP], [], RULES, forced=DOWN)[0] == DOWN


def test_outage_never_becomes_down_through_consolidation():
    """Tous les éléments inconnus (collecte perdue) : UNKNOWN, jamais DOWN."""
    assert consolidate_site([UNKNOWN, UNKNOWN, UNKNOWN], ["CRITICAL"], RULES)[0] == UNKNOWN


def test_rules_from_mapping_ignore_unknown_keys():
    rules = StatusRules.from_mapping({"down_confirm_s": 120, "inconnu": 1})
    assert rules.down_confirm_s == 120 and rules.up_confirm_s == 0


# --- Anti-rebond -----------------------------------------------------------------------


def test_down_is_confirmed_only_after_delay():
    rules = StatusRules(down_confirm_s=60)
    first = debounce(UP, NOW, None, None, DOWN, NOW, NOW, rules)
    assert first.status == UP and first.pending == DOWN and not first.changed

    later = debounce(UP, NOW, first.pending, first.pending_since, DOWN, NOW + timedelta(seconds=30),
                     NOW + timedelta(seconds=30), rules)
    assert later.status == UP and not later.changed

    confirmed = debounce(UP, NOW, first.pending, first.pending_since, DOWN, NOW + timedelta(seconds=61),
                         NOW + timedelta(seconds=61), rules)
    assert confirmed.status == DOWN and confirmed.changed
    assert confirmed.since == NOW  # horodatée à la première détection


def test_transition_to_unknown_is_never_delayed():
    rules = StatusRules(down_confirm_s=600)
    decision = debounce(UP, NOW, None, None, UNKNOWN, NOW, NOW, rules)
    assert decision.status == UNKNOWN and decision.changed


def test_no_change_when_candidate_equals_current():
    decision = debounce(UP, NOW, None, None, UP, NOW, NOW, RULES)
    assert not decision.changed and decision.since == NOW
