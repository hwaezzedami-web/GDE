"""Mapping ORM du schéma. La source de vérité est ``db/init/*.sql``.

``tests/test_schema.py`` échoue si une colonne de la base n'est pas mappée ici
(ou l'inverse).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

TS = TIMESTAMP(timezone=True)

SITE_STATUSES = ("UP", "DOWN", "DEGRADED", "UNKNOWN", "UNSUPERVISED")
ELEMENT_STATUSES = ("UP", "DOWN", "DEGRADED", "UNKNOWN")
ROLES = ("ADMIN", "SUPERVISOR", "VIEWER")
REF_STATUSES = ("IN_SERVICE", "TEMP_OFF", "PLANNED", "REMOVED", "OTHER")
ANOMALY_KINDS = (
    "UNKNOWN_SITE",
    "REMOVED_BUT_ACTIVE",
    "PLANNED_BUT_ACTIVE",
    "SUPERVISION_LOST",
    "NEVER_SUPERVISED",
)


class Geometry(UserDefinedType):
    """Colonne PostGIS minimale (lecture en EWKB hexadécimal ; utiliser ST_* en SQL)."""

    cache_ok = True

    def __init__(self, geom_type: str = "GEOMETRY", srid: int = 4326) -> None:
        self.geom_type = geom_type
        self.srid = srid

    def get_col_spec(self, **_: Any) -> str:
        return f"geometry({self.geom_type},{self.srid})"


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, datetime: TS}


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime]


class Wilaya(Base):
    __tablename__ = "wilayas"
    code: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name_fr: Mapped[str] = mapped_column(Text)
    name_ar: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    parent_code: Mapped[int | None] = mapped_column(SmallInteger)
    geom: Mapped[Any | None] = mapped_column(Geometry("MultiPolygon"))
    updated_at: Mapped[datetime]


class OmcSource(Base):
    __tablename__ = "omc_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    vendor: Mapped[str] = mapped_column(Text)
    connector: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    value_maps: Mapped[dict[str, Any]] = mapped_column(default=dict)
    stale_after_s: Mapped[int] = mapped_column(Integer, default=1800)
    interval_s: Mapped[int] = mapped_column(Integer, default=300)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_status: Mapped[str | None] = mapped_column(Text)
    last_run_at: Mapped[datetime | None]
    last_success_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    external_id: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    geom: Mapped[Any | None] = mapped_column(Geometry("Point"))
    wilaya_code: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("wilayas.code"))
    commune: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    vendor: Mapped[str | None] = mapped_column(Text)
    technologies: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    display_status: Mapped[str] = mapped_column(Text, default="UNKNOWN")
    status_since: Mapped[datetime | None]
    pending_status: Mapped[str | None] = mapped_column(Text)
    pending_since: Mapped[datetime | None]
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Référentiel (05_site_reference.sql)
    in_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    ref_status: Mapped[str | None] = mapped_column(Text)
    ref_source: Mapped[str | None] = mapped_column(Text)
    ref_updated_at: Mapped[datetime | None]
    ref_updated_by: Mapped[str | None] = mapped_column(Text)
    is_supervised: Mapped[bool] = mapped_column(Boolean, default=False)
    last_supervised_at: Mapped[datetime | None]
    dr: Mapped[str | None] = mapped_column(Text)


class SiteElement(Base):
    __tablename__ = "site_elements"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sites.id", ondelete="CASCADE"))
    source_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("omc_sources.id", ondelete="SET NULL"))
    ne_id: Mapped[str] = mapped_column(Text)
    ne_name: Mapped[str | None] = mapped_column(Text)
    ne_type: Mapped[str | None] = mapped_column(Text)
    technology: Mapped[str] = mapped_column(Text, default="OTHER")
    oper_status: Mapped[str] = mapped_column(Text, default="UNKNOWN")
    raw_status: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime | None]
    status_since: Mapped[datetime | None]
    pending_status: Mapped[str | None] = mapped_column(Text)
    pending_since: Mapped[datetime | None]
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class StatusHistory(Base):
    __tablename__ = "status_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sites.id", ondelete="CASCADE"))
    element_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("site_elements.id", ondelete="SET NULL"))
    old_status: Mapped[str | None] = mapped_column(Text)
    new_status: Mapped[str] = mapped_column(Text)
    changed_at: Mapped[datetime]
    source_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("omc_sources.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Alarm(Base):
    __tablename__ = "alarms"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("omc_sources.id", ondelete="SET NULL"))
    omc_alarm_id: Mapped[str] = mapped_column(Text)
    site_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sites.id", ondelete="SET NULL"))
    element_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("site_elements.id", ondelete="SET NULL"))
    ne_id: Mapped[str | None] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text, default="INDETERMINATE")
    description: Mapped[str | None] = mapped_column(Text)
    raised_at: Mapped[datetime | None]
    cleared_at: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen_at: Mapped[datetime | None]
    extra: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AlarmRule(Base):
    __tablename__ = "alarm_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("omc_sources.id", ondelete="CASCADE"))
    vendor: Mapped[str | None] = mapped_column(Text)
    match_code: Mapped[str | None] = mapped_column(Text)
    match_pattern: Mapped[str | None] = mapped_column(Text)
    effect: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text, default="SITE")
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validated_by: Mapped[str | None] = mapped_column(Text)
    validated_at: Mapped[datetime | None]
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict[str, Any]]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_by: Mapped[str | None] = mapped_column(Text)


class CollectionRun(Base):
    __tablename__ = "collection_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("omc_sources.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(Text, default="RUNNING")
    elements_count: Mapped[int] = mapped_column(Integer, default=0)
    alarms_count: Mapped[int] = mapped_column(Integer, default=0)
    unmapped_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)


class KpiSnapshot(Base):
    __tablename__ = "kpi_snapshots"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    taken_at: Mapped[datetime]
    scope: Mapped[str] = mapped_column(Text, default="GLOBAL")
    scope_key: Mapped[str] = mapped_column(Text, default="")
    total: Mapped[int] = mapped_column(Integer, default=0)
    up: Mapped[int] = mapped_column(Integer, default=0)
    down: Mapped[int] = mapped_column(Integer, default=0)
    degraded: Mapped[int] = mapped_column(Integer, default=0)
    unknown: Mapped[int] = mapped_column(Integer, default=0)
    unsupervised: Mapped[int] = mapped_column(Integer, default=0)
    availability: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))


class ServiceHeartbeat(Base):
    __tablename__ = "service_heartbeats"
    service: Mapped[str] = mapped_column(Text, primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default="VIEWER")
    can_export: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None]
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[datetime | None]
    password_changed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    at: Mapped[datetime] = mapped_column(server_default=func.now())
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    username: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    target: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    ip: Mapped[str | None] = mapped_column(Text)


class ReferenceImport(Base):
    __tablename__ = "reference_imports"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    imported_at: Mapped[datetime] = mapped_column(server_default=func.now())
    imported_by: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str | None] = mapped_column(Text)
    file_format: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text, default="UPLOAD")
    added: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    removed: Mapped[int] = mapped_column(Integer, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    mapping: Mapped[dict[str, Any]] = mapped_column(default=dict)
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)


class SiteAnomaly(Base):
    __tablename__ = "site_anomalies"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    site_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sites.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="OPEN")
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None]
    ack_by: Mapped[str | None] = mapped_column(Text)
    ack_at: Mapped[datetime | None]
    ack_comment: Mapped[str | None] = mapped_column(Text)


class SiteCodeAlias(Base):
    __tablename__ = "site_code_aliases"
    omc_code: Mapped[str] = mapped_column(Text, primary_key=True)
    site_code: Mapped[str] = mapped_column(
        Text, ForeignKey("sites.external_id", onupdate="CASCADE", ondelete="CASCADE")
    )
    comment: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
