"""Création du premier compte administrateur (uniquement si la table users est vide)."""
from __future__ import annotations

import logging

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import User
from ..security import check_password_policy, hash_password

log = logging.getLogger(__name__)


def ensure_initial_admin(db: Session) -> bool:
    # Plusieurs processus API démarrent en même temps : un seul crée le compte
    db.execute(text("SELECT pg_advisory_xact_lock(7421002)"))
    if db.scalar(select(func.count()).select_from(User)):
        return False
    s = get_settings()
    if not (s.initial_admin_username and s.initial_admin_password):
        log.warning("Aucun utilisateur en base. Définissez INITIAL_ADMIN_USERNAME / INITIAL_ADMIN_PASSWORD "
                    "ou utilisez : python -m app.cli create-user --role ADMIN")
        return False
    if err := check_password_policy(s.initial_admin_password):
        log.error("INITIAL_ADMIN_PASSWORD refusé : %s", err)
        return False
    db.add(User(username=s.initial_admin_username, full_name="Administrateur", role="ADMIN",
                password_hash=hash_password(s.initial_admin_password), can_export=True,
                must_change_password=True))
    log.warning("Compte administrateur initial « %s » créé : changez son mot de passe à la première connexion.",
                s.initial_admin_username)
    return True
