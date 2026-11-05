"""Dépendances FastAPI : session, utilisateur courant, contrôle des rôles."""

from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import decode_access_token

bearer = HTTPBearer(auto_error=False)

ROLE_LEVEL = {"VIEWER": 1, "SUPERVISOR": 2, "ADMIN": 3}


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _unauthorized(detail: str = "Authentification requise") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_user_any(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Utilisateur authentifié, même s'il doit encore changer son mot de passe."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _unauthorized("Jeton invalide ou expiré") from None
    user = db.get(User, user_id)
    if user is None or not user.is_active or payload.get("tv") != user.token_version:
        raise _unauthorized("Session expirée")
    return user


def current_user(user: User = Depends(current_user_any)) -> User:
    """Utilisateur authentifié dont le mot de passe n'est plus à changer."""
    if user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Changement de mot de passe requis",
        )
    return user


def require_role(minimum: str) -> Callable[[User], User]:
    """Exige un rôle au moins égal à ``minimum`` (VIEWER < SUPERVISOR < ADMIN)."""
    needed = ROLE_LEVEL[minimum]

    def checker(user: User = Depends(current_user)) -> User:
        if ROLE_LEVEL.get(user.role, 0) < needed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Droits insuffisants")
        return user

    return checker


require_viewer = require_role("VIEWER")
require_supervisor = require_role("SUPERVISOR")
require_admin = require_role("ADMIN")


def require_export(user: User = Depends(current_user)) -> User:
    """Export : droit ``can_export`` explicite (les administrateurs l'ont toujours)."""
    if user.role != "ADMIN" and not user.can_export:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Droit d'export requis")
    return user
