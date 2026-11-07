"""Modèles ORM alignés sur db/init/02_schema.sql (le SQL est la source de vérité).

La colonne générée sites.geom (PostGIS) n'est pas mappée : elle est calculée par
PostgreSQL et utilisée uniquement dans des requêtes SQL explicites.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    FetchedValue,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

STATUSES = ("UP", "DOWN", "DEGRADED", "UNKNOWN")
VENDORS = ("ERICSSON", "HUAWEI", "ZTE")
REF_STATUSES = ("IN_SERVICE", "TEMP_OFF", "PLANNED", "REMOVED", "OTHER")
ANOMALY_TYPES = ("UNKNOWN_SITE", "REMOVED_BUT_ACTIVE", "PLANNED_BUT_ACTIVE", "SUPERVISION_LOST", "NEVER_SUPERVISED")
TECHNOLOGIES = ("2G", "3G", "4G", "5G")
SEVERITIES = ("CRITICAL", "MAJOR", "MINOR", "WARNING", "INDETERMINATE")
ROLES = ("ADMIN", "SUPERVISOR", "VIEWER")
CONNECTOR_TYPES = ("manual_csv", "file_export", "sql_readonly", "ericsson", "huawei", "zte", "demo", "prometheus")


class Base(DeclarativeBase):
    pass


class Wilaya(Base):
    __tablename__ = "wilayas"
    code: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    name_ar: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str] = mapped_column(Text)
    chef_lieu: Mapped[str | None] = mapped_column(Text)
    center_lat: Mapped[float | None] = mapped_column(Float)
    center_lon: Mapped[float | None] = mapped_column(Float)
    parent_code: Mapped[int | None] = mapped_column(SmallInteger)
    created_year: Mapped[int | None] = mapped_column(SmallInteger)
    boundary_source: Mapped[str | None] = mapped_column(Text)


class OmcSource(Base):
    __tablename__ = "omc_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    vendor: Mapped[str] = mapped_column(Text)
    connector_type: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    integration_validated: Mapped[bool] = mapped_column(Boolean, default=False)
    poll_interval_s: Mapped[int] = mapped_column(Integer, default=300)
    stale_after_s: Mapped[int | None] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    sync_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class Site(Base):
    __tablename__ = "sites"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    external_id: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    vendor: Mapped[str] = mapped_column(Text)
    primary_source_id: Mapped[int | None] = mapped_column(ForeignKey("omc_sources.id"))
    wilaya_code: Mapped[int | None] = mapped_column(ForeignKey("wilayas.code"))
    commune: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    technologies: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    status: Mapped[str] = mapped_column(Text, default="UNKNOWN")
    status_since: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    status_reason: Mapped[str | None] = mapped_column(Text)
    pending_status: Mapped[str | None] = mapped_column(Text)
    pending_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    # Référentiel (v1.4)
    in_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    ref_status: Mapped[str | None] = mapped_column(Text)
    lifecycle: Mapped[str | None] = mapped_column(Text)
    dr: Mapped[str | None] = mapped_column(Text)
    ref_technologies: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    reference_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reference_import_id: Mapped[int | None] = mapped_column(BigInteger)
    is_supervised: Mapped[bool] = mapped_column(Boolean, default=False)
    last_supervised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Gestion manuelle (v1.5)
    ref_source: Mapped[str | None] = mapped_column(Text)
    ref_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ref_updated_by: Mapped[str | None] = mapped_column(Text)

    wilaya: Mapped[Wilaya | None] = relationship(lazy="joined")
    primary_source: Mapped[OmcSource | None] = relationship(lazy="joined")


class SiteElement(Base):
    __tablename__ = "site_elements"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    omc_source_id: Mapped[int] = mapped_column(ForeignKey("omc_sources.id"))
    external_id: Mapped[str] = mapped_column(Text)
    technology: Mapped[str] = mapped_column(Text)
    element_type: Mapped[str] = mapped_column(Text, default="NE")
    name: Mapped[str | None] = mapped_column(Text)
    oper_status: Mapped[str] = mapped_column(Text, default="UNKNOWN")
    raw_status: Mapped[str | None] = mapped_column(Text)
    status_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_communication_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())

    source: Mapped[OmcSource] = relationship(lazy="joined")


class StatusHistory(Base):
    __tablename__ = "status_history"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    entity_type: Mapped[str] = mapped_column(Text)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    element_id: Mapped[int | None] = mapped_column(ForeignKey("site_elements.id"))
    old_status: Mapped[str | None] = mapped_column(Text)
    new_status: Mapped[str] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    alarm_id: Mapped[int | None] = mapped_column(BigInteger)


class Alarm(Base):
    __tablename__ = "alarms"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    omc_source_id: Mapped[int] = mapped_column(ForeignKey("omc_sources.id"))
    external_alarm_id: Mapped[str] = mapped_column(Text)
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id"))
    element_id: Mapped[int | None] = mapped_column(ForeignKey("site_elements.id"))
    alarm_code: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text, default="INDETERMINATE")
    state: Mapped[str] = mapped_column(Text, default="ACTIVE")
    raised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)


class ReferenceImport(Base):
    __tablename__ = "reference_imports"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    username: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str | None] = mapped_column(Text)
    file_sha256: Mapped[str | None] = mapped_column(Text)
    file_format: Mapped[str | None] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    mapping: Mapped[dict] = mapped_column(JSONB, default=dict)
    counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    messages: Mapped[list] = mapped_column(JSONB, default=list)


class SiteAnomaly(Base):
    __tablename__ = "site_anomalies"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    anomaly_type: Mapped[str] = mapped_column(Text)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id"))
    site_external_id: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    state: Mapped[str] = mapped_column(Text, default="OPEN")
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[str | None] = mapped_column(Text)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)


class AlarmRule(Base):
    __tablename__ = "alarm_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor: Mapped[str] = mapped_column(Text)
    alarm_code: Mapped[str | None] = mapped_column(Text)
    text_pattern: Mapped[str | None] = mapped_column(Text)
    effect: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(Text, default="ELEMENT")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text)
    validated_by: Mapped[str | None] = mapped_column(Text)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_by: Mapped[str | None] = mapped_column(Text)


class CollectionRun(Base):
    __tablename__ = "collection_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    omc_source_id: Mapped[int] = mapped_column(ForeignKey("omc_sources.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="RUNNING")
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    sites_processed: Mapped[int] = mapped_column(Integer, default=0)
    elements_processed: Mapped[int] = mapped_column(Integer, default=0)
    alarms_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)


class KpiSnapshot(Base):
    __tablename__ = "kpi_snapshots"
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    vendor: Mapped[str] = mapped_column(Text, primary_key=True)
    wilaya_code: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    total: Mapped[int] = mapped_column(Integer)
    up: Mapped[int] = mapped_column(Integer)
    down: Mapped[int] = mapped_column(Integer)
    degraded: Mapped[int] = mapped_column(Integer)
    unknown: Mapped[int] = mapped_column(Integer)


class ServiceHeartbeat(Base):
    __tablename__ = "service_heartbeats"
    service: Mapped[str] = mapped_column(Text, primary_key=True)
    host: Mapped[str] = mapped_column(Text, primary_key=True)
    last_beat: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    info: Mapped[dict] = mapped_column(JSONB, default=dict)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True)
    full_name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text)
    can_export: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())

    @property
    def export_allowed(self) -> bool:
        return self.is_active and (self.role in ("ADMIN", "SUPERVISOR") or self.can_export)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    username: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    target: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(Text)


class SiteCodeAlias(Base):
    __tablename__ = "site_code_aliases"
    omc_code: Mapped[str] = mapped_column(Text, primary_key=True)
    site_external_id: Mapped[str] = mapped_column(ForeignKey("sites.external_id"))
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=FetchedValue())
