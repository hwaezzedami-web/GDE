"""Correspondance type de connecteur -> classe."""
from __future__ import annotations

from .connectors.base import BaseConnector, ConnectorNotConfigured, SourceSpec
from .connectors.demo import DemoConnector
from .connectors.file_export import FileExportConnector
from .connectors.prometheus import PrometheusConnector
from .connectors.sql_readonly import SqlReadOnlyConnector
from .connectors.vendor import EricssonConnector, HuaweiConnector, ZteConnector

CONNECTORS: dict[str, type[BaseConnector]] = {
    "file_export": FileExportConnector,
    "sql_readonly": SqlReadOnlyConnector,
    "ericsson": EricssonConnector,
    "huawei": HuaweiConnector,
    "zte": ZteConnector,
    "demo": DemoConnector,
    "prometheus": PrometheusConnector,
}


def build_connector(spec: SourceSpec) -> BaseConnector:
    if spec.connector_type == "manual_csv":
        raise ConnectorNotConfigured("Source alimentée manuellement par import CSV : pas de collecte automatique")
    cls = CONNECTORS.get(spec.connector_type)
    if cls is None:
        raise ConnectorNotConfigured(f"Type de connecteur inconnu : {spec.connector_type}")
    return cls(spec)
