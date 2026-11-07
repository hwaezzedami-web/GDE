"""Connecteur générique « base SQL en lecture seule ».

À utiliser uniquement si l'équipementier/l'exploitant met à disposition un accès
SQL documenté et autorisé (compte dédié en lecture seule, vue ou réplique).

Configuration :
  dsn_secret : nom du secret contenant l'URL SQLAlchemy (défaut : DSN)
               -> variable OMC_<CODE>_DSN, ex. postgresql+psycopg://user:pass@hote/base
  queries    : { inventory: "...", status: "...", alarms: "..." }
               Requêtes SELECT fournies par l'exploitant ; les colonnes renvoyées
               sont mappées via `columns` comme pour les fichiers d'export.
  statement_timeout_s : délai maximal par requête (défaut 120)

Garde-fous : seules les requêtes commençant par SELECT ou WITH sont acceptées,
et la transaction est ouverte en lecture seule quand le SGBD le permet.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from ..mapping import TabularMapper, ensure_configured
from ..model import CollectResult
from ..secrets import MissingSecret, get_secret
from .base import BaseConnector, ConnectorError, ConnectorNotConfigured

_READ_ONLY_RX = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_FORBIDDEN_RX = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|CALL|EXEC)\b",
                           re.IGNORECASE)


class SqlReadOnlyConnector(BaseConnector):
    def collect(self) -> CollectResult:
        from sqlalchemy import create_engine, text
        from sqlalchemy.exc import DBAPIError, OperationalError

        cfg = self.spec.config
        ensure_configured(cfg)
        queries = cfg.get("queries") or {}
        if not queries.get("inventory") and not queries.get("status"):
            raise ConnectorNotConfigured("queries.inventory ou queries.status requis")
        for name, q in queries.items():
            if not _READ_ONLY_RX.match(q or "") or _FORBIDDEN_RX.search(q or "") or ";" in q.strip().rstrip(";"):
                raise ConnectorNotConfigured(f"Requête « {name} » refusée : SELECT unique en lecture seule exigé")
        try:
            dsn = get_secret(self.spec.code, cfg.get("dsn_secret", "DSN"))
        except MissingSecret as exc:
            raise ConnectorNotConfigured(str(exc)) from exc

        timeout = int(cfg.get("statement_timeout_s", 120))
        engine = create_engine(dsn, pool_pre_ping=True)
        mapper = TabularMapper(cfg)
        res = CollectResult(inventory_complete=bool(cfg.get("inventory_complete", True)),
                            alarms_complete=bool(cfg.get("alarms_complete", "alarms" in queries)))
        now = datetime.now(timezone.utc)
        try:
            with engine.connect() as conn:
                if engine.dialect.name == "postgresql":
                    conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                    conn.exec_driver_sql(f"SET LOCAL statement_timeout = {timeout * 1000}")
                elif engine.dialect.name in ("mysql", "mariadb"):
                    conn.exec_driver_sql("SET SESSION TRANSACTION READ ONLY")
                for dataset in ("inventory", "status", "alarms"):
                    q = queries.get(dataset)
                    if not q:
                        if dataset == "inventory":
                            res.inventory_complete = False
                        continue
                    rows = [dict(r._mapping) for r in conn.execute(text(q.strip().rstrip(";")))]
                    res.details[dataset] = {"rows": len(rows)}
                    if dataset == "inventory":
                        mapper.map_inventory(rows, res, now)
                    elif dataset == "status":
                        mapper.map_status(rows, res, now)
                    else:
                        mapper.map_alarms(rows, res)
                conn.rollback()
        except OperationalError as exc:
            raise ConnectorError(f"Base OMC inaccessible : {exc.orig}", transient=True) from exc
        except DBAPIError as exc:
            raise ConnectorError(f"Erreur SQL : {exc.orig}", transient=False) from exc
        finally:
            engine.dispose()
        return res
