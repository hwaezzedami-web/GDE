"""Administration (phase 1) : utilisateurs et journal d'audit.

Les routes paramètres, règles d'alarmes, sources OMC et collectes arrivent aux phases suivantes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import client_ip, require_admin
from ..models import AuditLog, User
from ..security import PasswordPolicyError, check_password_policy, hash_password, record_audit
from .schemas import AuditOut, Page, ResetPasswordIn, UserCreateIn, UserOut, UserUpdateIn

router = APIRouter(prefix="/admin", tags=["admin"])


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utilisateur introuvable")
    return user


def _active_admins(db: Session) -> int:
    return db.scalar(
        select(func.count()).select_from(User).where(User.role == "ADMIN", User.is_active.is_(True))
    ) or 0


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(func.lower(User.username))))


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateIn, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> User:
    if db.scalar(select(func.count()).select_from(User).where(func.lower(User.username) == body.username.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cet identifiant existe déjà")
    try:
        check_password_policy(body.password, body.username)
    except PasswordPolicyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    user = User(
        username=body.username,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role=body.role,
        can_export=body.can_export or body.role == "ADMIN",
        must_change_password=True,
        password_changed_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    record_audit(
        db, "USER_CREATE", user=admin, target=user.username,
        details={"role": user.role, "can_export": user.can_export}, ip=client_ip(request),
    )
    db.commit()
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdateIn,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    user = _get_user(db, user_id)
    changes = body.model_dump(exclude_unset=True)
    removing_admin = user.role == "ADMIN" and user.is_active and (
        changes.get("role", "ADMIN") != "ADMIN" or changes.get("is_active", True) is False
    )
    if removing_admin and _active_admins(db) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Impossible de retirer le dernier administrateur actif")
    before = {k: getattr(user, k) for k in changes}
    for key, value in changes.items():
        setattr(user, key, value)
    if user.role == "ADMIN":
        user.can_export = True
    if before.get("role") != user.role or changes.get("is_active") is False:
        user.token_version += 1  # droits modifiés : reconnexion imposée
    user.updated_at = datetime.now(UTC)
    record_audit(
        db, "USER_UPDATE", user=admin, target=user.username,
        details={"before": before, "after": changes}, ip=client_ip(request),
    )
    db.commit()
    return user


@router.post("/users/{user_id}/reset-password", response_model=UserOut)
def reset_password(
    user_id: int,
    body: ResetPasswordIn,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    user = _get_user(db, user_id)
    try:
        check_password_policy(body.new_password, user.username)
    except PasswordPolicyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = True
    user.failed_logins = 0
    user.locked_until = None
    user.token_version += 1
    user.password_changed_at = datetime.now(UTC)
    record_audit(db, "USER_PASSWORD_RESET", user=admin, target=user.username, ip=client_ip(request))
    db.commit()
    return user


@router.post("/users/{user_id}/unlock", response_model=UserOut)
def unlock_user(
    user_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> User:
    user = _get_user(db, user_id)
    user.failed_logins = 0
    user.locked_until = None
    record_audit(db, "USER_UNLOCK", user=admin, target=user.username, ip=client_ip(request))
    db.commit()
    return user


@router.get("/audit", response_model=Page[AuditOut])
def list_audit(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    action: str | None = Query(default=None, max_length=64),
    username: str | None = Query(default=None, max_length=100),
    since: datetime | None = None,
    until: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> Page[AuditOut]:
    conditions = []
    if action:
        conditions.append(AuditLog.action == action.upper())
    if username:
        conditions.append(func.lower(AuditLog.username) == username.lower())
    if since:
        conditions.append(AuditLog.at >= since)
    if until:
        conditions.append(AuditLog.at < until)
    total = db.scalar(select(func.count()).select_from(AuditLog).where(*conditions)) or 0
    rows = db.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page[AuditOut](
        items=[AuditOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size
    )
