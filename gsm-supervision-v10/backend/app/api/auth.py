"""Authentification : connexion, profil, changement de mot de passe."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import audit, get_current_user
from ..models import User
from ..security import check_password_policy, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Hash factice : temps de réponse identique que l'utilisateur existe ou non
_DUMMY_HASH = hash_password("dummy-password-for-timing")


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: dict


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


def user_public(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email,
        "role": u.role, "can_export": u.export_allowed, "must_change_password": u.must_change_password,
        "is_active": u.is_active, "last_login_at": u.last_login_at,
    }


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    now = datetime.now(timezone.utc)
    user = db.scalar(select(User).where(func.lower(User.username) == body.username.strip().lower()))
    generic = HTTPException(401, "Identifiant ou mot de passe incorrect.")
    if user is None:
        verify_password(body.password, _DUMMY_HASH)
        audit(db, None, "LOGIN_FAILED", body.username[:64], {"reason": "unknown_user"}, request)
        db.commit()
        raise generic
    if user.locked_until and user.locked_until > now:
        audit(db, user, "LOGIN_REFUSED_LOCKED", user.username, {}, request)
        db.commit()
        raise HTTPException(423, "Compte temporairement verrouillé après plusieurs échecs. Réessayez plus tard.")
    if not verify_password(body.password, user.password_hash) or not user.is_active:
        user.failed_logins += 1
        details = {"failed_logins": user.failed_logins}
        if user.failed_logins >= s.login_max_failures:
            user.locked_until = now + timedelta(minutes=s.login_lock_minutes)
            user.failed_logins = 0
            details["locked_until"] = user.locked_until.isoformat()
        audit(db, user, "LOGIN_FAILED", user.username, details, request)
        db.commit()
        raise generic
    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    token, exp = create_access_token(user.id, user.username, user.role, user.token_version)
    audit(db, user, "LOGIN", user.username, {}, request)
    db.commit()
    return TokenOut(access_token=token, expires_at=exp, user=user_public(user))


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_public(user)


@router.post("/logout")
def logout(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Révoque toutes les sessions de l'utilisateur (incrément de token_version)."""
    u = db.get(User, user.id)
    u.token_version += 1
    audit(db, u, "LOGOUT", u.username, {}, request)
    db.commit()
    return {"ok": True}


@router.post("/change-password")
def change_password(body: PasswordChangeIn, request: Request,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    u = db.get(User, user.id)
    if not verify_password(body.current_password, u.password_hash):
        raise HTTPException(400, "Mot de passe actuel incorrect.")
    if err := check_password_policy(body.new_password):
        raise HTTPException(400, err)
    if body.new_password == body.current_password:
        raise HTTPException(400, "Le nouveau mot de passe doit être différent de l'actuel.")
    u.password_hash = hash_password(body.new_password)
    u.must_change_password = False
    u.token_version += 1
    audit(db, u, "PASSWORD_CHANGED", u.username, {}, request)
    db.commit()
    token, exp = create_access_token(u.id, u.username, u.role, u.token_version)
    return {"access_token": token, "token_type": "bearer", "expires_at": exp, "user": user_public(u)}
