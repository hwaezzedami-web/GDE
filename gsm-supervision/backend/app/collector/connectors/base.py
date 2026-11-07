"""Contrat commun des connecteurs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..model import CollectResult

PLACEHOLDER = "A_COMPLETER"


class ConnectorError(RuntimeError):
    """Échec de collecte. La source passe en FAILED ; les équipements ne sont pas modifiés."""


class ConnectorNotConfigured(ConnectorError):
    """Configuration incomplète (valeurs A_COMPLETER) : la collecte est refusée."""


@dataclass(frozen=True)
class SourceSpec:
    id: int
    code: str
    vendor: str
    connector: str
    config: dict[str, Any]
    value_maps: dict[str, Any]
    stale_after_s: int
    interval_s: int


def ensure_configured(config: Any, path: str = "config") -> None:
    """Refuse toute configuration contenant encore un ``A_COMPLETER``."""
    if isinstance(config, dict):
        for key, value in config.items():
            ensure_configured(value, f"{path}.{key}")
    elif isinstance(config, list):
        for index, value in enumerate(config):
            ensure_configured(value, f"{path}[{index}]")
    elif isinstance(config, str) and PLACEHOLDER in config:
        raise ConnectorNotConfigured(f"{path} n'est pas renseigné ({PLACEHOLDER})")


class Connector(ABC):
    name: str

    @abstractmethod
    def collect(self, spec: SourceSpec, now: datetime) -> CollectResult:
        """Lit la source et renvoie un instantané normalisé. Lève ConnectorError en cas d'échec."""
