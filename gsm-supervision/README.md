# Supervision GSM Algérie

Application web de supervision géographique des sites radio 2G/3G/4G/5G (69 wilayas, carte hors ligne),
avec collecte **en lecture seule** depuis les OMC Ericsson, Huawei et ZTE.

> Projet construit phase par phase (voir `CLAUDE.md`). **État actuel : phase 1 — socle.**

## Phase 1 : contenu

- Docker Compose : `db` (PostgreSQL 16 + PostGIS 3.4) et `api` (FastAPI).
- Schéma SQL idempotent `db/init/01..06` (schéma version 4), rejoué à chaque démarrage.
- Référentiel des 69 wilayas (`db/reference/wilayas.csv`) ; contours à construire avec
  `scripts/build_wilaya_reference.py` (voir `db/reference/README.md`).
- Modèles SQLAlchemy (`backend/app/models.py`), contrôlés par `test_schema.py`.
- CLI : `python -m app.cli init-db | create-user | unlock-user`.
- Authentification JWT, mots de passe bcrypt, verrouillage après échecs, changement de mot de passe
  imposé, rôles ADMIN / SUPERVISOR / VIEWER, droit `can_export`, journal d'audit.

## Démarrage (Docker)

```bash
cp .env.example .env      # puis remplir POSTGRES_PASSWORD, JWT_SECRET (≥ 32 car.), INITIAL_ADMIN_PASSWORD
docker compose up -d --build
```

L'API écoute sur `http://127.0.0.1:8000` ; documentation sur `/api/docs`.
**Ne jamais lancer `docker compose down -v`** : cela supprime la base.

## Tests

Les tests utilisent une vraie base PostgreSQL + PostGIS (`gsm_test_<pid>`, créée puis supprimée) :

```bash
cd backend
pip install -r requirements-dev.txt
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres pytest
```

## Règles du projet

- Ne jamais inventer d'API, de commande OMC, d'OID SNMP ni de format d'export : valeurs `A_COMPLETER`
  bloquantes tant qu'elles ne viennent pas de données réelles.
- Aucun secret dans le code (`.env`, `.env.omc`, variantes `*_FILE`).
- Accès OMC strictement en lecture ; rien à installer sur les OMC.
- Perte de collecte ≠ panne radio : collecte en échec ⇒ état INCONNU, jamais DOWN.
- Les données réelles de l'opérateur ne vont jamais dans le dépôt.
