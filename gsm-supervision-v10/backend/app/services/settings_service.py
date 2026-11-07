"""Lecture/écriture des paramètres applicatifs (table app_settings) avec valeurs par défaut."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULTS: dict[str, dict[str, Any]] = {
    "status_rules": {
        # Données considérées périmées après ce délai si la source n'a pas son propre seuil
        "default_stale_after_s": 1800,
        # Anti-rebond : délai pendant lequel un état DOWN (resp. UP) doit persister avant d'être confirmé
        "down_confirm_s": 0,
        "up_confirm_s": 0,
        # 'ignore' : l'état du site est calculé sur les équipements dont l'état est connu
        # 'degrade': un site UP dont un équipement est UNKNOWN passe DEGRADED
        "unknown_elements_policy": "ignore",
        # Une alarme active CRITICAL/MAJOR sur un site UP le fait passer DEGRADED (orange)
        "major_alarm_degrades": True,
        # Une partie des technologies en panne => DEGRADED (sinon le site reste UP)
        "partial_down_is_degraded": True,
    },
    "collector": {
        "evaluate_every_s": 60,
        "snapshot_every_s": 900,
        "max_retries": 3,
        "retry_backoff_s": 10,
        "history_retention_days": 730,
        "runs_retention_days": 90,
        "snapshots_retention_days": 400,
    },
    "reference": {
        # Valeur brute du cycle de vie (fichier) -> catégorie. À VALIDER avec l'exploitant :
        # le sens exact de « halte », « construit », « not_on_air » est propre à l'opérateur.
        "lifecycle_map": {
            "en_air": "IN_SERVICE",
            "halte": "TEMP_OFF", "not_on_air": "TEMP_OFF",
            "planning": "PLANNED", "acquisition": "PLANNED", "construction": "PLANNED",
            "implementation": "PLANNED", "construit": "PLANNED",
            "desinstalle": "REMOVED", "vandalise": "REMOVED",
        },
        "lifecycle_unknown": "OTHER",          # valeur absente de la table ci-dessus
        "lifecycle_missing": "IN_SERVICE",     # fichier sans colonne cycle de vie
        # Wilaya : celle du fichier (référentiel de l'opérateur) ou celle déduite des coordonnées (69 wilayas)
        "wilaya_from": "file",
        # Rapprocher « 5474 » (OMC) et « 05474 » (référentiel) quand la correspondance est unique
        "match_leading_zeros": True,
        "supervision_lost_days": 2,
        "detect_never_supervised": False,      # à activer quand tous les OMC sont raccordés
        # Synchronisation complète refusée si elle retire plus de ce pourcentage de sites (sauf confirmation)
        "max_removal_pct": 10,
        # Dossier surveillé (service de collecte) : import automatique du fichier le plus récent
        "watch_enabled": False,
        "watch_mode": "update",
        "watch_interval_s": 300,
    },
}

VALIDATORS = {
    "status_rules": {
        "default_stale_after_s": (int, 60, 7 * 86400),
        "down_confirm_s": (int, 0, 86400),
        "up_confirm_s": (int, 0, 86400),
        "unknown_elements_policy": (str, ("ignore", "degrade")),
        "major_alarm_degrades": (bool,),
        "partial_down_is_degraded": (bool,),
    },
    "collector": {
        "evaluate_every_s": (int, 15, 3600),
        "snapshot_every_s": (int, 60, 86400),
        "max_retries": (int, 0, 10),
        "retry_backoff_s": (int, 1, 600),
        "history_retention_days": (int, 30, 3650),
        "runs_retention_days": (int, 7, 3650),
        "snapshots_retention_days": (int, 7, 3650),
    },
    "reference": {
        "lifecycle_map": ("map", ("IN_SERVICE", "TEMP_OFF", "PLANNED", "REMOVED", "OTHER")),
        "lifecycle_unknown": (str, ("IN_SERVICE", "TEMP_OFF", "PLANNED", "REMOVED", "OTHER")),
        "lifecycle_missing": (str, ("IN_SERVICE", "TEMP_OFF", "PLANNED", "REMOVED", "OTHER")),
        "wilaya_from": (str, ("file", "coordinates")),
        "match_leading_zeros": (bool,),
        "supervision_lost_days": (int, 1, 365),
        "detect_never_supervised": (bool,),
        "max_removal_pct": (int, 0, 100),
        "watch_enabled": (bool,),
        "watch_mode": (str, ("update", "sync")),
        "watch_interval_s": (int, 60, 86400),
    },
}


def get_setting(db: Session, key: str) -> dict[str, Any]:
    row = db.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": key}).scalar()
    merged = dict(DEFAULTS.get(key, {}))
    if row:
        merged.update(row)
    return merged


def validate_setting(key: str, value: dict[str, Any]) -> dict[str, Any]:
    if key not in VALIDATORS:
        raise ValueError(f"Paramètre inconnu : {key}")
    spec = VALIDATORS[key]
    clean: dict[str, Any] = {}
    for k, v in value.items():
        if k not in spec:
            raise ValueError(f"Clé inconnue « {k} » pour {key}")
        rule = spec[k]
        typ = rule[0]
        if typ is bool:
            if not isinstance(v, bool):
                raise ValueError(f"{k} doit être un booléen")
        elif typ is int:
            if isinstance(v, bool) or not isinstance(v, int):
                raise ValueError(f"{k} doit être un entier")
            lo, hi = rule[1], rule[2]
            if not lo <= v <= hi:
                raise ValueError(f"{k} doit être compris entre {lo} et {hi}")
        elif typ is str:
            if v not in rule[1]:
                raise ValueError(f"{k} doit valoir : {', '.join(rule[1])}")
        elif typ == "map":
            if not isinstance(v, dict) or len(v) > 200:
                raise ValueError(f"{k} doit être une table valeur -> catégorie")
            for kk, vv in v.items():
                if not isinstance(kk, str) or not kk.strip() or len(kk) > 80 or vv not in rule[1]:
                    raise ValueError(f"{k} : « {kk} » -> « {vv} » invalide (catégories : {', '.join(rule[1])})")
            v = {kk.strip().lower(): vv for kk, vv in v.items()}
        clean[k] = v
    return clean


def set_setting(db: Session, key: str, value: dict[str, Any], username: str) -> dict[str, Any]:
    clean = validate_setting(key, value)
    merged = get_setting(db, key)
    merged.update(clean)
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy import bindparam

    db.execute(
        text("""INSERT INTO app_settings (key, value, updated_at, updated_by)
                VALUES (:k, :v, now(), :u)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                    updated_at = now(), updated_by = EXCLUDED.updated_by""").bindparams(
            bindparam("v", type_=JSONB)),
        {"k": key, "v": merged, "u": username},
    )
    return merged
