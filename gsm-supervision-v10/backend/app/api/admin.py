"""Administration : utilisateurs, sources OMC, règles d'états, import CSV, journaux.

Aucune action de cette API ne modifie la configuration des équipements réseau :
les sources OMC sont accédées en lecture seule par le service de collecte.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, get_current_user, require_admin, require_supervisor
from ..models import CONNECTOR_TYPES, ROLES, VENDORS, AlarmRule, OmcSource, User
from ..security import check_password_policy, hash_password
from ..services.csv_import import import_sites_csv
from ..services.settings_service import get_setting, set_setting
from ..services.status_engine import evaluate_sites
from .auth import user_public

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Clés de configuration de source qui ne doivent jamais contenir de secret
_SECRET_KEY_RX = re.compile(r"(pass|secret|token|key|pwd|credential)", re.IGNORECASE)


# --------------------------------------------------------------------------- utilisateurs
class UserIn(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9._-]{3,64}$")
    full_name: str | None = Field(None, max_length=120)
    email: str | None = Field(None, max_length=200)
    role: str
    can_export: bool = False
    password: str = Field(min_length=1, max_length=128)

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        if v not in ROLES:
            raise ValueError("rôle invalide")
        return v


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=120)
    email: str | None = Field(None, max_length=200)
    role: str | None = None
    can_export: bool | None = None
    is_active: bool | None = None
    password: str | None = Field(None, max_length=128)

    @field_validator("role")
    @classmethod
    def _role(cls, v):
        if v is not None and v not in ROLES:
            raise ValueError("rôle invalide")
        return v


@router.get("/users")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [user_public(u) | {"locked_until": u.locked_until, "created_at": u.created_at}
            for u in db.scalars(select(User).order_by(User.username))]


@router.post("/users", status_code=201)
def create_user(body: UserIn, request: Request, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    if db.scalar(select(User).where(func.lower(User.username) == body.username.lower())):
        raise HTTPException(409, "Ce nom d'utilisateur existe déjà.")
    if err := check_password_policy(body.password):
        raise HTTPException(400, err)
    u = User(username=body.username, full_name=body.full_name, email=body.email, role=body.role,
             can_export=body.can_export, password_hash=hash_password(body.password),
             must_change_password=True)
    db.add(u)
    db.flush()
    audit(db, admin, "USER_CREATED", u.username, {"role": u.role, "can_export": u.can_export}, request)
    db.commit()
    return user_public(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, request: Request, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "Utilisateur introuvable")
    changes = body.model_dump(exclude_unset=True)
    if u.id == admin.id and (changes.get("is_active") is False or changes.get("role", "ADMIN") != "ADMIN"):
        raise HTTPException(400, "Vous ne pouvez pas retirer vos propres droits d'administrateur.")
    pwd = changes.pop("password", None)
    if pwd:
        if err := check_password_policy(pwd):
            raise HTTPException(400, err)
        u.password_hash = hash_password(pwd)
        u.must_change_password = True
        u.failed_logins = 0
        u.locked_until = None
    for k, v in changes.items():
        setattr(u, k, v)
    if pwd or "role" in changes or changes.get("is_active") is False:
        u.token_version += 1          # révocation des sessions en cours
    u.updated_at = datetime.now(timezone.utc)
    audit(db, admin, "USER_UPDATED", u.username,
          {k: v for k, v in changes.items()} | ({"password_reset": True} if pwd else {}), request)
    db.commit()
    return user_public(u)


# --------------------------------------------------------------------------- paramètres
@router.get("/settings")
def get_settings_all(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {k: get_setting(db, k) for k in ("status_rules", "collector", "reference")}


@router.put("/settings/{key}")
def put_setting(key: str, body: dict, request: Request, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    try:
        value = set_setting(db, key, body, admin.username)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    audit(db, admin, "SETTINGS_UPDATED", key, body, request)
    if key == "status_rules":
        evaluate_sites(db)
    elif key == "reference":
        from ..reference.service import reclassify
        reclassify(db)
    db.commit()
    return value


# --------------------------------------------------------------------------- règles d'alarmes
class AlarmRuleIn(BaseModel):
    vendor: str
    alarm_code: str | None = Field(None, max_length=100)
    text_pattern: str | None = Field(None, max_length=300)
    effect: str = Field(pattern="^(DOWN|DEGRADED)$")
    scope: str = Field("ELEMENT", pattern="^(ELEMENT|SITE)$")
    enabled: bool = True
    note: str | None = Field(None, max_length=500)

    @field_validator("vendor")
    @classmethod
    def _vendor(cls, v):
        if v not in VENDORS:
            raise ValueError("équipementier invalide")
        return v

    @field_validator("text_pattern")
    @classmethod
    def _rx(cls, v):
        if v:
            try:
                re.compile(v)
            except re.error as exc:
                raise ValueError(f"expression régulière invalide : {exc}")
        return v


def _rule_dict(r: AlarmRule) -> dict:
    return {c: getattr(r, c) for c in ("id", "vendor", "alarm_code", "text_pattern", "effect", "scope",
                                       "enabled", "note", "validated_by", "validated_at", "created_at")}


@router.get("/alarm-rules")
def list_rules(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_rule_dict(r) for r in db.scalars(select(AlarmRule).order_by(AlarmRule.vendor, AlarmRule.id))]


@router.post("/alarm-rules", status_code=201)
def create_rule(body: AlarmRuleIn, request: Request, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    if not body.alarm_code and not body.text_pattern:
        raise HTTPException(422, "Indiquer un code d'alarme ou un motif de texte.")
    r = AlarmRule(**body.model_dump())     # créée NON validée : sans effet tant qu'elle n'est pas validée
    db.add(r)
    db.flush()
    audit(db, admin, "ALARM_RULE_CREATED", str(r.id), body.model_dump(), request)
    db.commit()
    return _rule_dict(r)


@router.put("/alarm-rules/{rule_id}")
def update_rule(rule_id: int, body: AlarmRuleIn, request: Request, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    r = db.get(AlarmRule, rule_id)
    if r is None:
        raise HTTPException(404, "Règle introuvable")
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    r.validated_at = None                  # toute modification exige une nouvelle validation
    r.validated_by = None
    audit(db, admin, "ALARM_RULE_UPDATED", str(r.id), body.model_dump(), request)
    evaluate_sites(db)
    db.commit()
    return _rule_dict(r)


@router.post("/alarm-rules/{rule_id}/validate")
def validate_rule(rule_id: int, request: Request, admin: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    r = db.get(AlarmRule, rule_id)
    if r is None:
        raise HTTPException(404, "Règle introuvable")
    r.validated_at = datetime.now(timezone.utc)
    r.validated_by = admin.username
    audit(db, admin, "ALARM_RULE_VALIDATED", str(r.id), _rule_dict(r) | {"validated_at": None, "created_at": None},
          request)
    db.flush()
    evaluate_sites(db)
    db.commit()
    return _rule_dict(r)


@router.delete("/alarm-rules/{rule_id}")
def delete_rule(rule_id: int, request: Request, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    r = db.get(AlarmRule, rule_id)
    if r is None:
        raise HTTPException(404, "Règle introuvable")
    info = _rule_dict(r) | {"validated_at": None, "created_at": None}
    db.delete(r)
    audit(db, admin, "ALARM_RULE_DELETED", str(rule_id), info, request)
    db.flush()
    evaluate_sites(db)
    db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------- sources OMC
class OmcSourceIn(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_-]{2,40}$")
    name: str = Field(min_length=1, max_length=120)
    vendor: str
    connector_type: str
    enabled: bool = False
    poll_interval_s: int = Field(300, ge=30, le=86400)
    stale_after_s: int | None = Field(None, ge=60, le=7 * 86400)
    config: dict = Field(default_factory=dict)
    integration_validated: bool = False

    @field_validator("vendor")
    @classmethod
    def _v(cls, v):
        if v not in VENDORS:
            raise ValueError("équipementier invalide")
        return v

    @field_validator("connector_type")
    @classmethod
    def _c(cls, v):
        if v not in CONNECTOR_TYPES:
            raise ValueError("type de connecteur invalide")
        return v

    @field_validator("config")
    @classmethod
    def _no_secret(cls, v):
        def walk(d, path=""):
            if isinstance(d, dict):
                for k, val in d.items():
                    if _SECRET_KEY_RX.search(str(k)) and not str(k).endswith("_env") and not str(k).endswith(
                            "_ref") and val not in (None, ""):
                        raise ValueError(
                            f"La clé « {path}{k} » ressemble à un secret : les secrets doivent être fournis "
                            "par variables d'environnement (OMC_<CODE>_…), jamais dans la configuration.")
                    walk(val, f"{path}{k}.")
        walk(v)
        return v


def _source_dict(o: OmcSource) -> dict:
    return {c: getattr(o, c) for c in (
        "id", "code", "name", "vendor", "connector_type", "enabled", "is_demo", "integration_validated",
        "poll_interval_s", "stale_after_s", "config", "sync_requested_at", "last_attempt_at",
        "last_success_at", "last_status", "last_error", "consecutive_failures", "created_at", "updated_at")}


@router.get("/omc-sources")
def list_sources(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_source_dict(o) for o in db.scalars(select(OmcSource).order_by(OmcSource.vendor, OmcSource.code))]


@router.post("/omc-sources", status_code=201)
def create_source(body: OmcSourceIn, request: Request, admin: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    if db.scalar(select(OmcSource).where(OmcSource.code == body.code)):
        raise HTTPException(409, "Ce code de source existe déjà.")
    o = OmcSource(**body.model_dump())
    db.add(o)
    db.flush()
    audit(db, admin, "OMC_SOURCE_CREATED", o.code, body.model_dump(), request)
    db.commit()
    return _source_dict(o)


@router.put("/omc-sources/{source_id}")
def update_source(source_id: int, body: OmcSourceIn, request: Request, admin: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    o = db.get(OmcSource, source_id)
    if o is None:
        raise HTTPException(404, "Source introuvable")
    if body.code != o.code:
        raise HTTPException(400, "Le code d'une source ne peut pas être modifié.")
    for k, v in body.model_dump().items():
        setattr(o, k, v)
    o.updated_at = datetime.now(timezone.utc)
    audit(db, admin, "OMC_SOURCE_UPDATED", o.code, body.model_dump(), request)
    db.commit()
    return _source_dict(o)


@router.post("/omc-sources/{source_id}/sync")
def request_sync(source_id: int, request: Request, user: User = Depends(require_supervisor),
                 db: Session = Depends(get_db)):
    """Demande une synchronisation immédiate (exécutée par le service de collecte)."""
    o = db.get(OmcSource, source_id)
    if o is None:
        raise HTTPException(404, "Source introuvable")
    if not o.enabled:
        raise HTTPException(400, "Source désactivée.")
    o.sync_requested_at = datetime.now(timezone.utc)
    audit(db, user, "OMC_SYNC_REQUESTED", o.code, {}, request)
    db.commit()
    return {"ok": True, "sync_requested_at": o.sync_requested_at}


@router.get("/collection-runs")
def collection_runs(source: str | None = Query(None), page: int = Query(1, ge=1),
                    page_size: int = Query(50, ge=1, le=500),
                    _: User = Depends(require_supervisor), db: Session = Depends(get_db)):
    cond, p = "TRUE", {"lim": page_size, "off": (page - 1) * page_size}
    if source:
        cond = "o.code = :src"
        p["src"] = source.upper()
    total = db.execute(text(f"""SELECT count(*) FROM collection_runs r JOIN omc_sources o
                                ON o.id = r.omc_source_id WHERE {cond}"""), p).scalar()
    rows = db.execute(text(f"""
        SELECT r.id, o.code AS omc_code, o.vendor, r.started_at, r.finished_at, r.status, r.attempts,
               r.sites_processed, r.elements_processed, r.alarms_processed, r.records_rejected,
               r.error_message, r.details,
               extract(epoch FROM coalesce(r.finished_at, now()) - r.started_at)::numeric(10,1) AS duration_s
        FROM collection_runs r JOIN omc_sources o ON o.id = r.omc_source_id
        WHERE {cond} ORDER BY r.started_at DESC LIMIT :lim OFFSET :off"""), p).mappings().all()
    return {"total": total, "items": [dict(r) for r in rows]}


# --------------------------------------------------------------------------- import CSV
@router.post("/import/sites-csv")
async def import_csv(request: Request, file: UploadFile = File(...),
                     default_source: str = Query("IMPORT-CSV", pattern=r"^[A-Z0-9_-]{2,40}$"),
                     admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (20 Mo maximum).")
    try:
        report = import_sites_csv(db, content, default_source=default_source)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc))
    audit(db, admin, "CSV_IMPORT", file.filename,
          {"rows": report.rows, "accepted": report.accepted, "rejected": len(report.rejected)}, request)
    db.commit()
    return {"rows": report.rows, "accepted": report.accepted, "rejected": report.rejected[:200],
            "sources": report.sources}


# --------------------------------------------------------------------------- audit
@router.get("/audit")
def audit_log(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
              action: str | None = Query(None, max_length=50), username: str | None = Query(None, max_length=64),
              _: User = Depends(require_admin), db: Session = Depends(get_db)):
    cond, p = ["TRUE"], {"lim": page_size, "off": (page - 1) * page_size}
    if action:
        cond.append("action = :a")
        p["a"] = action.upper()
    if username:
        cond.append("username = :u")
        p["u"] = username
    w = " AND ".join(cond)
    total = db.execute(text(f"SELECT count(*) FROM audit_log WHERE {w}"), p).scalar()
    rows = db.execute(text(f"""SELECT id, at, username, action, target, details, ip FROM audit_log
                               WHERE {w} ORDER BY at DESC, id DESC LIMIT :lim OFFSET :off"""), p).mappings().all()
    return {"total": total, "items": [dict(r) for r in rows]}
