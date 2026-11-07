"""Interface commune des connecteurs OMC."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..model import CollectResult


class ConnectorError(Exception):
    """Erreur de collecte. transient=True : nouvelle tentative possible (réseau, timeout…)."""

    def __init__(self, message: str, transient: bool = True):
        super().__init__(message)
        self.transient = transient


class ConnectorNotConfigured(ConnectorError):
    """Configuration incomplète (profil non renseigné, secret manquant…) : inutile de réessayer."""

    def __init__(self, message: str):
        super().__init__(message, transient=False)


@dataclass
class SourceSpec:
    id: int
    code: str
    vendor: str
    connector_type: str
    config: dict = field(default_factory=dict)
    poll_interval_s: int = 300
    is_demo: bool = False


class BaseConnector(ABC):
    """Un connecteur lit une source OMC (en lecture seule) et renvoie un CollectResult normalisé.

    Il ne doit jamais écrire en base ni modifier quoi que ce soit côté OMC.
    """

    #: valeurs possibles : 'ERICSSON', 'HUAWEI', 'ZTE' ou None (générique)
    vendor: str | None = None

    def __init__(self, spec: SourceSpec):
        self.spec = spec
        if self.vendor and spec.vendor != self.vendor:
            raise ConnectorNotConfigured(
                f"Le connecteur {type(self).__name__} est réservé à {self.vendor} (source {spec.code} = {spec.vendor})")

    @abstractmethod
    def collect(self) -> CollectResult:
        ...

    def test_connection(self) -> str:
        res = self.collect()
        return (f"OK — {len(res.sites)} sites, {len(res.elements)} équipements, {len(res.alarms)} alarmes, "
                f"{len(res.rejected)} lignes rejetées")

    def close(self) -> None:
        pass
