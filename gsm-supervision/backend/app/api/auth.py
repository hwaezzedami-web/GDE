"""Authentification : /api/auth/login, /me, /logout, /change-password."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import client_ip, current_user_any
from ..models import User
from ..security import (
    PasswordPolicyError,
    burn_password_check,
    check_password_policy,
    create_access_token,
    hash_password,
    record_audit,
    verify_password,
)
from .schemas import ChangePasswordIn, LoginIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID = "Identifiant ou mot de passe incorrect"


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    settings = get_settings()
    ip = client_ip(request)
    now = datetime.now(UTC)
    user = db.scalar(
        select(User).where(func.lower(User.username) == body.username.strip().lower()).with_for_update()
    )

    if user is None:
        burn_password_check(body.password)
        record_audit(db, "LOGIN_FAILED", username=body.username[:100], details={"reason": "unknown_user"}, ip=ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)

    if user.locked_until and user.locked_until > now:
        burn_password_check(body.password)
        record_audit(db, "LOGIN_REFUSED_LOCKED", user=user, ip=ip)
        db.commit()
        raise HTTPException(status.HTTP_423_LOCKED, "Compte verrouillé temporairement après trop d'échecs")

    if not verify_password(body.password, user.password_hash) or not user.is_active:
        user.failed_logins += 1
        details = {"failures": user.failed_logins, "reason": "inactive" if user.is_active is False else "bad_password"}
        if user.failed_logins >= settings.login_max_failures:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            user.failed_logins = 0
            record_audit(db, "USER_LOCKED", user=user, details=details, ip=ip)
        else:
            record_audit(db, "LOGIN_FAILED", user=user, details=details, ip=ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    record_audit(db, "LOGIN", user=user, ip=ip)
    db.commit()
    token, expires_in = create_access_token(user)
    return TokenOut(
        access_token=token,
        expires_in=expires_in,
        must_change_password=user.must_change_password,
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user_any)) -> User:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, user: User = Depends(current_user_any), db: Session = Depends(get_db)) -> None:
    # Invalide tous les jetons déjà émis pour ce compte.
    user.token_version += 1
    record_audit(db, "LOGOUT", user=user, ip=client_ip(request))
    db.commit()


@router.post("/change-password", response_model=TokenOut)
def change_password(
    body: ChangePasswordIn,
    request: Request,
    user: User = Depends(current_user_any),
    db: Session = Depends(get_db),
) -> TokenOut:
    if not verify_password(body.current_password, user.password_hash):
        record_audit(db, "PASSWORD_CHANGE_FAILED", user=user, ip=client_ip(request))
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mot de passe actuel incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Le nouveau mot de passe doit être différent")
    try:
        check_password_policy(body.new_password, user.username)
    except PasswordPolicyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(UTC)
    user.token_version += 1
    record_audit(db, "PASSWORD_CHANGE", user=user, ip=client_ip(request))
    db.commit()
    token, expires_in = create_access_token(user)
    return TokenOut(
        access_token=token,
        expires_in=expires_in,
        must_change_password=False,
        user=UserOut.model_validate(user),
    )
