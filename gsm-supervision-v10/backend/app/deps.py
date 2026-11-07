"""Dépendances FastAPI : authentification, rôles, audit."""
from __future__ import annotations

from typing import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, User
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(msg: str = "Session expirée ou invalide, veuillez vous reconnecter.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=msg,
                         headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    user = _authenticate(creds, db)
    if user.must_change_password and not request.url.path.startswith("/api/auth/"):
        raise HTTPException(status_code=403, detail="Changement de mot de passe requis avant de continuer.")
    return user


def _authenticate(creds: HTTPAuthorizationCredentials | None, db: Session) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise _unauthorized("Authentification requise.")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Session expirée, veuillez vous reconnecter.")
    except jwt.PyJWTError:
        raise _unauthorized()
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active or user.token_version != payload.get("tv"):
        raise _unauthorized()
    return user


def require_roles(*roles: str) -> Callable[[User], User]:
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Droits insuffisants pour cette opération.")
        return user
    return _dep


require_admin = require_roles("ADMIN")
require_supervisor = require_roles("ADMIN", "SUPERVISOR")


def require_export(user: User = Depends(get_current_user)) -> User:
    if not user.export_allowed:
        raise HTTPException(status_code=403, detail="Vous n'avez pas l'autorisation d'exporter des données.")
    return user


def client_ip(request: Request) -> str | None:
    # Derrière le reverse proxy nginx (X-Real-IP positionné par nginx uniquement)
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


def audit(db: Session, user: User | None, action: str, target: str | None = None,
          details: dict | None = None, request: Request | None = None) -> None:
    db.add(AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else None,
        action=action,
        target=target,
        details=details or {},
        ip=client_ip(request) if request else None,
    ))
