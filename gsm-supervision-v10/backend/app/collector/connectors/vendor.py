"""Connecteurs Ericsson / Huawei / ZTE.

Chaque connecteur équipementier :
  1. charge le profil de son équipementier (collector/profiles/<vendor>.yaml),
     qui décrit les correspondances de colonnes et de valeurs ;
  2. fusionne la configuration propre à la source (omc_sources.config), prioritaire ;
  3. délègue la lecture à l'interface effectivement disponible :
       - "file_export"  : fichiers d'export CSV (local/SFTP)
       - "sql_readonly" : accès SQL en lecture seule autorisé
       - "api"          : NON IMPLÉMENTÉ — à développer à partir de la documentation
                          officielle de l'interface nord (NBI) de votre version d'OMC.

IMPORTANT : les profils livrés contiennent des valeurs « A_COMPLETER ». Tant
qu'elles ne sont pas renseignées à partir des exports RÉELS, le connecteur
refuse de s'exécuter (ConnectorNotConfigured). Aucun format d'export n'est
supposé. Le drapeau omc_sources.integration_validated ne doit être positionné
qu'après validation sur données réelles (docs/07_VALIDATION.md).
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

from ..model import CollectResult
from .base import BaseConnector, ConnectorNotConfigured
from .file_export import FileExportConnector
from .sql_readonly import SqlReadOnlyConnector

PROFILE_DIR = Path(__file__).resolve().parents[1] / "profiles"


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class VendorConnector(BaseConnector):
    profile_name: str = ""

    def __init__(self, spec):
        super().__init__(spec)
        profile_file = spec.config.get("profile_file") or PROFILE_DIR / f"{self.profile_name}.yaml"
        try:
            profile = yaml.safe_load(Path(profile_file).read_text(encoding="utf-8")) or {}
        except FileNotFoundError:
            raise ConnectorNotConfigured(f"Profil introuvable : {profile_file}")
        self.effective_config = deep_merge(profile, spec.config)

    def _delegate(self) -> BaseConnector:
        interface = self.effective_config.get("interface")
        delegate_spec = copy.copy(self.spec)
        delegate_spec.config = self.effective_config
        if interface == "file_export":
            return FileExportConnector(delegate_spec)
        if interface == "sql_readonly":
            return SqlReadOnlyConnector(delegate_spec)
        if interface == "api":
            raise ConnectorNotConfigured(
                f"Interface API {self.vendor} non implémentée : fournir la documentation de l'interface nord "
                "(NBI) de votre OMC et un environnement de test pour la développer.")
        raise ConnectorNotConfigured(
            f"interface non définie pour {self.spec.code} (file_export, sql_readonly ou api)")

    def collect(self) -> CollectResult:
        res = self._delegate().collect()
        res.details["profile"] = self.profile_name
        return res


class EricssonConnector(VendorConnector):
    vendor = "ERICSSON"
    profile_name = "ericsson"


class HuaweiConnector(VendorConnector):
    vendor = "HUAWEI"
    profile_name = "huawei"


class ZteConnector(VendorConnector):
    vendor = "ZTE"
    profile_name = "zte"
