"""Commandes d'administration en ligne de commande.

  python -m app.cli init-db                      Crée/actualise le schéma (scripts db/init/*.sql)
  python -m app.cli create-user --username X --role ADMIN [--export]
  python -m app.cli import-csv FICHIER.csv [--source CODE]
  python -m app.cli seed-demo [--csv data/test/sites_fictifs.csv]
  python -m app.cli test-source CODE              Teste une source OMC SANS rien écrire en base
  python -m app.cli run-source CODE               Exécute une collecte immédiate
  python -m app.cli evaluate                      Recalcule l'état de tous les sites
  python -m app.cli status                        Résumé (sites par état, sources)
  python -m app.cli load-boundaries F.geojson     Contours officiels personnalisés (remplacent ceux d'OSM)
  python -m app.cli reassign-wilayas [--all]      Rattache les sites à leur wilaya d'après les contours
  python -m app.cli reference-import F.kmz [--mode update|sync] [--dry-run] [--code-digits N]
                                                  Importe le référentiel de sites (KMZ, KML, XLSX, CSV, GeoJSON)
  python -m app.cli reconcile                     Recalcule les anomalies référentiel <-> OMC
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from sqlalchemy import func, select, text

from .config import get_settings
from .db import apply_sql_scripts, session_scope
from .logging_setup import setup_logging


def cmd_init_db(_):
    applied = apply_sql_scripts()
    print("Scripts appliqués :", ", ".join(applied))


def cmd_create_user(a):
    from .models import ROLES, User
    from .security import check_password_policy, hash_password

    if a.role not in ROLES:
        sys.exit(f"Rôle invalide ({', '.join(ROLES)})")
    pwd = os.environ.get("NEW_USER_PASSWORD") or getpass.getpass("Mot de passe : ")
    if err := check_password_policy(pwd):
        sys.exit(err)
    with session_scope() as db:
        if db.scalar(select(User).where(func.lower(User.username) == a.username.lower())):
            sys.exit("Utilisateur déjà existant")
        db.add(User(username=a.username, full_name=a.full_name, role=a.role, can_export=a.export,
                    password_hash=hash_password(pwd), must_change_password=not a.no_change))
    print(f"Utilisateur {a.username} ({a.role}) créé.")


def cmd_import_csv(a):
    from .services.csv_import import import_sites_csv

    with session_scope() as db:
        rep = import_sites_csv(db, Path(a.file).read_bytes(), default_source=a.source.upper())
    print(f"{rep.accepted}/{rep.rows} lignes importées, {len(rep.rejected)} rejet(s)")
    for r in rep.rejected[:50]:
        print("  -", r)


def cmd_seed_demo(a):
    from .services.csv_import import import_sites_csv

    csv_path = Path(a.csv or os.path.join(get_settings().data_dir, "test", "sites_fictifs.csv"))
    with session_scope() as db:
        rep = import_sites_csv(db, csv_path.read_bytes(), default_source="DEMO", connector_type="demo",
                               is_demo=True, poll_interval_s=a.interval)
    print(f"Données FICTIVES chargées : {rep.accepted} sites — sources : {', '.join(rep.sources)}")
    print("Les sources DEMO-* sont activées : le service de collecte simulera des pannes.")


def _source(db, code):
    from .models import OmcSource

    o = db.scalar(select(OmcSource).where(OmcSource.code == code.upper()))
    if o is None:
        sys.exit(f"Source {code} introuvable")
    return o


def cmd_test_source(a):
    from .collector.connectors.base import ConnectorError
    from .collector.registry import build_connector
    from .collector.runner import _spec

    with session_scope() as db:
        spec = _spec(_source(db, a.code))
    try:
        conn = build_connector(spec)
        res = conn.collect()
        conn.close()
    except ConnectorError as exc:
        sys.exit(f"ÉCHEC : {exc}")
    print(f"OK — {len(res.sites)} sites, {len(res.elements)} équipements, {len(res.alarms)} alarmes")
    print(f"Rejets : {len(res.rejected)} ; avertissements : {len(res.warnings)}")
    for m in (res.rejected + res.warnings)[:30]:
        print("  -", m)
    statuses = {}
    for e in res.elements:
        statuses[e.oper_status] = statuses.get(e.oper_status, 0) + 1
    print("Répartition des états reçus :", json.dumps(statuses))
    for e in res.elements[: a.sample]:
        print("  échantillon :", e.site_external_id, e.external_id, e.technology, e.raw_status, "->", e.oper_status)


def cmd_run_source(a):
    from .collector.runner import run_source

    with session_scope() as db:
        sid = _source(db, a.code).id
    print("Résultat :", run_source(sid))


def cmd_evaluate(_):
    from .services.status_engine import evaluate_sites

    with session_scope() as db:
        print(evaluate_sites(db))


def cmd_load_boundaries(a):
    """Charge les contours des wilayas depuis un GeoJSON officiel (EPSG:4326)."""
    from .services.geo import load_wilaya_boundaries

    data = json.loads(Path(a.file).read_text(encoding="utf-8"))
    with session_scope() as db:
        n, skipped = load_wilaya_boundaries(db, data, a.code_property)
    print(f"{n} contour(s) chargé(s).")
    for s in skipped[:20]:
        print("  ignoré :", s)


def cmd_reassign_wilayas(a):
    from .services.geo import reassign_site_wilayas

    with session_scope() as db:
        n = reassign_site_wilayas(db, overwrite=a.all)
    print(f"{n} site(s) rattaché(s) à une nouvelle wilaya.")


def cmd_reference_import(a):
    from .reference.service import apply_plan, build_plan, plan_summary
    from .services.settings_service import get_setting

    content = Path(a.file).read_bytes()
    mapping = json.loads(a.mapping) if a.mapping else None
    with session_scope() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(7421004)"))
        plan = build_plan(db, Path(a.file).name, content, mapping, a.mode, a.code_digits, a.sheet)
        summ = plan_summary(plan, get_setting(db, "reference"))
        print("Correspondance des colonnes :")
        for k, v in summ["mapping"].items():
            print(f"  {k:<13} <- {v or '—'}")
        print("Compteurs :", json.dumps(summ["counts"], ensure_ascii=False))
        for w in summ["warnings"]:
            print("  ATTENTION :", w)
        for x in summ["invalid"][:20]:
            print(f"  ligne {x['line']} rejetée ({x['code'] or '?'}) : {x['reason']}")
        if a.dry_run:
            print("Simulation : rien n'a été écrit.")
            db.rollback()
            return
        res = apply_plan(db, plan, a.mode, "cli", "CLI", Path(a.file).name, a.confirm_large_removal)
        print(res["status"], res.get("message", ""), json.dumps(res.get("anomalies", {}), ensure_ascii=False))
        if res["status"] == "REFUSED":
            sys.exit(2)


def cmd_reconcile(_):
    from .reference.anomalies import reconcile_anomalies

    with session_scope() as db:
        print(json.dumps(reconcile_anomalies(db), ensure_ascii=False))


def cmd_status(_):
    with session_scope() as db:
        for r in db.execute(text("SELECT status, count(*) FROM sites WHERE is_active GROUP BY 1 ORDER BY 1")):
            print(f"{r[0]:<9} {r[1]}")
        for r in db.execute(text("SELECT code, connector_type, enabled, last_status, last_success_at FROM omc_sources")):
            print(" ", *r)


def main(argv=None):
    s = get_settings()
    setup_logging("cli", s.log_level)
    p = argparse.ArgumentParser(prog="python -m app.cli", description="Administration GSM Supervision")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db").set_defaults(fn=cmd_init_db)
    u = sub.add_parser("create-user")
    u.add_argument("--username", required=True)
    u.add_argument("--role", default="VIEWER")
    u.add_argument("--full-name")
    u.add_argument("--export", action="store_true", help="Autoriser les exports")
    u.add_argument("--no-change", action="store_true", help="Ne pas imposer de changement au 1er login")
    u.set_defaults(fn=cmd_create_user)
    i = sub.add_parser("import-csv")
    i.add_argument("file")
    i.add_argument("--source", default="IMPORT-CSV")
    i.set_defaults(fn=cmd_import_csv)
    d = sub.add_parser("seed-demo")
    d.add_argument("--csv")
    d.add_argument("--interval", type=int, default=60)
    d.set_defaults(fn=cmd_seed_demo)
    t = sub.add_parser("test-source")
    t.add_argument("code")
    t.add_argument("--sample", type=int, default=5)
    t.set_defaults(fn=cmd_test_source)
    r = sub.add_parser("run-source")
    r.add_argument("code")
    r.set_defaults(fn=cmd_run_source)
    sub.add_parser("evaluate").set_defaults(fn=cmd_evaluate)
    lb = sub.add_parser("load-boundaries", help="Charger les contours des wilayas (GeoJSON)")
    lb.add_argument("file")
    lb.add_argument("--code-property", default="code", help="Propriété GeoJSON portant le code wilaya")
    lb.set_defaults(fn=cmd_load_boundaries)
    rw = sub.add_parser("reassign-wilayas", help="Rattacher les sites à leur wilaya d'après les contours")
    rw.add_argument("--all", action="store_true",
                    help="Recalculer pour TOUS les sites (sinon : seulement ceux sans wilaya)")
    rw.set_defaults(fn=cmd_reassign_wilayas)
    ri = sub.add_parser("reference-import", help="Importer le référentiel de sites")
    ri.add_argument("file")
    ri.add_argument("--mode", choices=("update", "sync"), default="update")
    ri.add_argument("--mapping", help='JSON {"code": "Code site", "latitude": "Lat", …} (sinon détection)')
    ri.add_argument("--code-digits", type=int, help="Compléter les codes numériques à N chiffres (zéros de tête)")
    ri.add_argument("--sheet", help="Feuille Excel")
    ri.add_argument("--dry-run", action="store_true", help="Afficher le différentiel sans rien écrire")
    ri.add_argument("--confirm-large-removal", action="store_true")
    ri.set_defaults(fn=cmd_reference_import)
    sub.add_parser("reconcile").set_defaults(fn=cmd_reconcile)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
