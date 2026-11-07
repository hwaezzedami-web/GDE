"""Lecture des secrets des sources OMC — jamais dans le code ni en base.

Pour une source de code « HUAWEI-OMC-1 », les secrets sont lus dans :
    OMC_HUAWEI_OMC_1_<NOM>            (variable d'environnement)
    OMC_HUAWEI_OMC_1_<NOM>_FILE       (chemin d'un fichier, ex. secret Docker /run/secrets/…)
Noms usuels : USERNAME, PASSWORD, PRIVATE_KEY_PATH, PRIVATE_KEY_PASSPHRASE, DSN.
"""
from __future__ import annotations

import os
import re


class MissingSecret(Exception):
    pass


def env_prefix(source_code: str) -> str:
    return "OMC_" + re.sub(r"[^A-Z0-9]", "_", source_code.upper()) + "_"


def get_secret(source_code: str, name: str, required: bool = True) -> str | None:
    key = env_prefix(source_code) + name.upper()
    val = os.environ.get(key)
    if val is None and os.environ.get(key + "_FILE"):
        with open(os.environ[key + "_FILE"], encoding="utf-8") as fh:
            val = fh.read().strip()
    if val is None and required:
        raise MissingSecret(f"Secret manquant : définir la variable d'environnement {key} (ou {key}_FILE)")
    return val
