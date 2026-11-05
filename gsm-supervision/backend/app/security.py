"""Mots de passe (bcrypt), jetons JWT et journal d'audit."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AuditLog, User

# bcrypt ne prend en compte que les 72 premiers octets : on refuse au-delà
MAX_PASSWORD_BYTES = 72


class PasswordPolicyError(ValueError):
    pass


def hash_password(password: str) -> str:
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise PasswordPolicyError("Mot de passe trop long (72 octets au maximum)")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except ValueError:
        return False


# Hachage factice : égalise le temps de réponse quand l'utilisateur n'existe pas.
_DUMMY_HASH = bcrypt.hashpw(b"utilisateur-inexistant", bcrypt.gensalt(rounds=12)).decode("ascii")


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def check_password_policy(password: str, username: str | None = None) -> None:
    """Lève PasswordPolicyError si le mot de passe est trop faible."""
    settings = get_settings()
    errors = []
    if len(password) < settings.password_min_length:
        errors.append(f"au moins {settings.password_min_length} caractères")
    if not re.search(r"[A-Za-zÀ-ÿ]", password):
        errors.append("au moins une lettre")
    if not re.search(r"\d", password):
        errors.append("au moins un chiffre")
    if username and username.lower() in password.lower():
        errors.append("ne pas contenir l'identifiant")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        errors.append("72 octets au maximum")
    if errors:
        raise PasswordPolicyError("Mot de passe refusé : " + ", ".join(errors))


def create_access_token(user: User) -> tuple[str, int]:
    settings = get_settings()
    now = datetime.now(UTC)
    expires_in = settings.jwt_expire_minutes * 60
    payload = {
        "sub": str(user.id),
        "usr": user.username,
        "role": user.role,
        "tv": user.token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "exp", "iat"]},
    )


def record_audit(
    session: Session,
    action: str,
    *,
    user: User | None = None,
    username: str | None = None,
    target: str | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Ajoute une entrée d'audit dans la transaction courante (commit par l'appelant)."""
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            username=user.username if user else username,
            action=action,
            target=target,
            details=details or {},
            ip=ip,
        )
    )
