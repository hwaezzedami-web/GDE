"""Ligne de commande : ``python -m app.cli <commande>``.

Commandes (phase 1) :
  init-db       crée / met à jour le schéma, charge les wilayas, crée l'administrateur initial
  create-user   crée un utilisateur (mot de passe demandé ou lu dans GSM_NEW_PASSWORD)
  unlock-user   déverrouille un compte
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import sys
from datetime import UTC, datetime

from sqlalchemy import func, select, text

from .config import ConfigError, get_settings
from .db import get_engine, get_sessionmaker
from .logging_setup import setup_logging
from .models import ROLES, User
from .security import PasswordPolicyError, check_password_policy, hash_password, record_audit
from .services.bootstrap import init_db

log = logging.getLogger("app.cli")


def cmd_init_db(_: argparse.Namespace) -> int:
    settings = get_settings()
    result = init_db(
        get_engine(),
        settings.db_dir,
        settings.initial_admin_username,
        settings.initial_admin_password,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _read_password(username: str) -> str:
    password = os.environ.get("GSM_NEW_PASSWORD")
    if not password:
        password = getpass.getpass(f"Mot de passe pour {username} : ")
        if password != getpass.getpass("Confirmation : "):
            raise SystemExit("Les mots de passe ne correspondent pas")
    check_password_policy(password, username)
    return password


def cmd_create_user(args: argparse.Namespace) -> int:
    with get_sessionmaker()() as session, session.begin():
        exists = session.scalar(
            select(func.count()).select_from(User).where(func.lower(User.username) == args.username.lower())
        )
        if exists:
            print(f"L'utilisateur {args.username} existe déjà", file=sys.stderr)
            return 1
        password = _read_password(args.username)
        session.add(
            User(
                username=args.username,
                full_name=args.full_name,
                password_hash=hash_password(password),
                role=args.role,
                can_export=args.can_export or args.role == "ADMIN",
                must_change_password=not args.no_force_change,
                password_changed_at=datetime.now(UTC),
            )
        )
        record_audit(session, "USER_CREATE", username="cli", target=args.username, details={"role": args.role})
    print(f"Utilisateur {args.username} créé ({args.role})")
    return 0


def cmd_unlock_user(args: argparse.Namespace) -> int:
    with get_sessionmaker()() as session, session.begin():
        user = session.scalar(select(User).where(func.lower(User.username) == args.username.lower()))
        if user is None:
            print(f"Utilisateur {args.username} introuvable", file=sys.stderr)
            return 1
        user.failed_logins = 0
        user.locked_until = None
        record_audit(session, "USER_UNLOCK", username="cli", target=user.username)
    print(f"Compte {args.username} déverrouillé")
    return 0


def cmd_seed_demo(_: argparse.Namespace) -> int:
    from .collector.runner import ensure_demo_source, run_source

    with get_sessionmaker()() as session:
        source_id = ensure_demo_source(session)
        outcome = run_source(session, source_id)
    print(
        json.dumps(
            {
                "source": outcome.source_code,
                "status": outcome.status,
                "error": outcome.error,
                "sites_created": outcome.ingest.sites_created if outcome.ingest else 0,
                "elements": outcome.ingest.elements if outcome.ingest else 0,
                "alarms": outcome.ingest.alarms if outcome.ingest else 0,
                "transitions": outcome.evaluation.site_transitions if outcome.evaluation else 0,
            },
            ensure_ascii=False,
        )
    )
    return 0 if outcome.status == "OK" else 1


def cmd_collect(args: argparse.Namespace) -> int:
    from .collector.runner import run_source

    with get_sessionmaker()() as session:
        source_id = session.scalar(
            text("SELECT id FROM omc_sources WHERE code = :c"), {"c": args.code}
        )
        if source_id is None:
            print(f"Source {args.code} introuvable", file=sys.stderr)
            return 1
        outcome = run_source(session, source_id)
    print(json.dumps({"source": outcome.source_code, "status": outcome.status, "error": outcome.error}, ensure_ascii=False))
    return 0 if outcome.status == "OK" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Supervision GSM : administration")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="initialise ou met à jour la base (idempotent)").set_defaults(func=cmd_init_db)

    p = sub.add_parser("create-user", help="crée un utilisateur")
    p.add_argument("username")
    p.add_argument("--role", choices=ROLES, default="VIEWER")
    p.add_argument("--full-name")
    p.add_argument("--can-export", action="store_true")
    p.add_argument("--no-force-change", action="store_true", help="ne pas imposer le changement de mot de passe")
    p.set_defaults(func=cmd_create_user)

    p = sub.add_parser("unlock-user", help="déverrouille un compte")
    p.add_argument("username")
    p.set_defaults(func=cmd_unlock_user)

    sub.add_parser("seed-demo", help="crée la source de démonstration fictive et la collecte").set_defaults(
        func=cmd_seed_demo
    )

    p = sub.add_parser("collect", help="lance une collecte pour une source (code)")
    p.add_argument("code")
    p.set_defaults(func=cmd_collect)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = get_settings()
    except ConfigError as exc:
        print(f"Erreur de configuration : {exc}", file=sys.stderr)
        return 2
    setup_logging(settings.log_level, settings.log_dir, name="cli")
    try:
        return args.func(args)
    except PasswordPolicyError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
