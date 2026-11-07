"""Lecture des paramètres de l'application (table app_settings)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from .status_engine import StatusRules


def get_setting(session: Session, key: str) -> dict | None:
    value = session.scalar(text("SELECT value FROM app_settings WHERE key = :k"), {"k": key})
    return value


def get_status_rules(session: Session) -> StatusRules:
    return StatusRules.from_mapping(get_setting(session, "status_rules") or {})
