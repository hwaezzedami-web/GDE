# CLAUDE.md — Supervision GSM Algérie

Langue du projet : **français** (interface, messages, documentation, commentaires).
Cahier des charges complet : `docs/00_cahier_des_charges.md`.

## Méthode

Construction phase par phase (§15 du cahier des charges). À la fin de chaque phase : tests verts,
puis validation par l'utilisateur avant la phase suivante.

| Phase | Contenu | État |
|---|---|---|
| 1 | Socle : Compose, schéma SQL, wilayas, modèles, `init-db`, auth, utilisateurs, audit | fait |
| 2 | Moteur d'états, ingestion, connecteur `demo`, `seed-demo` | à faire |
| 3 | API sites / carte / tableau de bord / exports, filtres communs | à faire |
| 4 | Frontend React (carte pylônes 3D, fiches, tableau, dashboard, alarmes, admin) | à faire |
| 5 | Collecteur, connecteurs `prometheus` / `file_export`, profils `A_COMPLETER`, `test-source` | à faire |
| 6 | Référentiel : parsers, import en deux temps, rapprochement, anomalies | à faire |
| 7 | Gestion des sites, sites inconnus, alias, modales accessibles | à faire |
| 8 | Pile Prometheus, exporteur par fichiers | à faire |
| 9 | Récepteur de traps SNMP, AlarmBook | à faire |
| 10 | Documentation `docs/01..13` | à faire |

## Règles non négociables

1. Ne jamais inventer d'API, commande OMC, OID SNMP ou format d'export : `A_COMPLETER` bloquant.
2. Intégration déclarée opérationnelle seulement après test sur données réelles.
3. Aucun secret dans le code (`.env`, `.env.omc`, `OMC_<CODE>_*`, variantes `*_FILE`).
4. OMC en lecture seule, rien à installer dessus, jamais exposés sur Internet.
5. Perte de collecte ≠ panne radio (INCONNU, jamais DOWN).
6. Aucune donnée réelle de l'opérateur dans le dépôt, les tests ou la doc.

## Conventions

- `db/init/*.sql` est la source de vérité, scripts idempotents ; toute colonne doit être mappée dans
  `backend/app/models.py` (`test_schema.py`). `schema_version` = 4.
- SQL toujours avec paramètres liés. Toute action sensible passe par `record_audit()`.
- Verrous consultatifs : 7421001 init-db, 7421003 rapprochement, 7421004 import du référentiel.
- Tests : `cd backend && pytest` (base PostgreSQL + PostGIS réelle via `TEST_DATABASE_URL`).
