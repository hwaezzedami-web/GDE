"""Mots de passe (bcrypt) et jetons de session (JWT signés, durée limitée)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def check_password_policy(password: str) -> str | None:
    """Retourne un message d'erreur si le mot de passe est trop faible, sinon None."""
    s = get_settings()
    if len(password) < s.password_min_length:
        return f"Le mot de passe doit contenir au moins {s.password_min_length} caractères."
    classes = sum([
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ])
    if classes < 3:
        return "Le mot de passe doit combiner au moins 3 types : minuscules, majuscules, chiffres, symboles."
    if len(password.encode("utf-8")) > 72:
        return "Le mot de passe ne doit pas dépasser 72 octets."
    return None


def create_access_token(user_id: int, username: str, role: str, token_version: int) -> tuple[str, datetime]:
    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=s.access_token_minutes)
    payload = {
        "sub": str(user_id),
        "usr": username,
        "role": role,
        "tv": token_version,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm), exp


def decode_access_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub"]})
