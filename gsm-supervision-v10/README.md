# Supervision GSM Algérie

Application web de supervision géographique des sites radio 2G / 3G / 4G / 5G : carte interactive de l'Algérie (69 wilayas, utilisable sans accès Internet), état UP / DOWN / DÉGRADÉ / INCONNU de chaque site, historique des pannes, alarmes, tableau de bord et collecte automatique depuis les OMC Ericsson, Huawei et ZTE. Le **référentiel des sites** de l'opérateur s'importe et se met à jour depuis un fichier **KMZ, KML, Excel, CSV ou GeoJSON** ; les écarts avec les OMC (site remonté mais absent du référentiel, site démonté encore actif, supervision perdue…) sont détectés automatiquement.

![Carte](docs/screenshots/2_fiche_tableau.png)

> **État de l'intégration OMC — à lire avant tout déploiement**
> Le socle complet est opérationnel et testé (base, API, moteur d'états, collecte planifiée, interface, sécurité, déploiement). Les connecteurs **Ericsson, Huawei et ZTE ne sont PAS déclarés opérationnels** : conformément au cahier des charges, aucun format d'export, API ou commande OMC n'a été supposé. Les profils livrés contiennent des valeurs `A_COMPLETER` qui bloquent volontairement leur exécution tant qu'elles n'ont pas été renseignées à partir des exports réels puis validées (voir [docs/08_INFORMATIONS_A_FOURNIR.md](docs/08_INFORMATIONS_A_FOURNIR.md)).
> Les données fournies (`data/test/sites_fictifs.csv`, sources `DEMO-*`) sont **entièrement fictives**.

## Démarrage rapide (Docker)

```bash
cp .env.example .env            # renseigner POSTGRES_PASSWORD, JWT_SECRET, INITIAL_ADMIN_PASSWORD
cp .env.omc.example .env.omc    # secrets OMC (peut rester vide pour la démonstration)
docker compose up -d --build
docker compose exec api python -m app.cli seed-demo    # optionnel : 3 000 sites FICTIFS + simulateur de pannes
```

Interface : `http://<serveur>:8080` — se connecter avec `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` (changement de mot de passe imposé à la première connexion).

Importer ensuite la liste des sites : menu **Référentiel → Importer** (KMZ Google Earth, Excel…), voir [docs/11_REFERENTIEL.md](docs/11_REFERENTIEL.md).

## Démarrage en développement

```bash
# Base PostgreSQL 14+ avec PostGIS, puis :
cd backend && pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/gsm ENVIRONMENT=development DATA_DIR=../data
python -m app.cli init-db
python -m app.cli create-user --username admin --role ADMIN --export
python -m app.cli seed-demo
uvicorn app.main:app --reload --port 8000          # API  (documentation : http://localhost:8000/api/docs)
python -m app.collector.runner                      # service de collecte (autre terminal)
cd ../frontend && npm install && npm run dev        # interface : http://localhost:5173
```

Tests : `cd backend && TEST_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/postgres pytest` (63 tests sur PostgreSQL/PostGIS réel ; le test d'intégration Prometheus s'active avec `PROMETHEUS_TEST_URL`).

## Contenu

| Chemin | Rôle |
|---|---|
| `backend/app/api/` | API REST FastAPI : authentification, sites, carte, tableau de bord, alarmes, exports, administration |
| `backend/app/services/status_engine.py` | Moteur d'états UP / DOWN / DEGRADED / UNKNOWN, anti-rebond, historisation |
| `backend/app/services/ingest.py` | Intégration des collectes en base sans doublon (upserts) |
| `backend/app/reference/` | Référentiel des sites : lecture KMZ/KML/Excel/CSV/GeoJSON, différentiel, import, anomalies de rapprochement OMC |
| `referentiel-depot/` | Dossier de dépôt pour l'import automatique du référentiel (données réelles : non versionné) |
| `backend/app/collector/` | Service de collecte : planification, reprise sur erreur, connecteurs |
| `backend/app/collector/connectors/` | `prometheus` (Prometheus / Alertmanager), `file_export` (CSV local/SFTP), `sql_readonly`, `ericsson` / `huawei` / `zte`, `demo` |
| `backend/app/collector/profiles/` | Profils équipementiers **à compléter** à partir des exports réels |
| `backend/tests/` | Tests automatisés (moteur, connecteurs, ingestion, API, sécurité, géographie) |
| `frontend/` | Interface React + Leaflet (carte, fiches, tableau, tableau de bord, alarmes, administration) |
| `db/init/` | Scripts SQL de création (schéma = source de vérité), référentiel et contours des **69 wilayas** |
| `frontend/public/geo/` | Fond de carte hors ligne (pays voisins) |
| `scripts/` | Reconstruction du référentiel des wilayas et du fond de carte |
| `deploy/prometheus/`, `docker-compose.prometheus.yml` | Pile Prometheus + Alertmanager optionnelle, règles d'alertes |
| `tools/omc_textfile_exporter/`, `scripts/omc_exporter.sh` | Exporteur d'OMC par fichiers (export CSV → node_exporter → Prometheus), configuration à partir de l'export réel |
| `tools/snmp_trap_receiver/`, `scripts/snmp_alarms.sh` | Réception des alarmes d'OMC par traps SNMP (snmptrapd) → alarmes actives → Prometheus |
| `tools/demo_exporter/` | Exporteur Prometheus de démonstration (données fictives, implémentation de référence du contrat de métriques) |
| `data/test/` | Jeu de données FICTIF et son générateur |
| `deploy/` | nginx, unités systemd, scripts de sauvegarde / restauration |
| `docs/` | Documentation technique, utilisateur, exploitation, validation |

## Documentation

1. [Architecture](docs/01_ARCHITECTURE.md)
2. [Modèle de données](docs/02_MODELE_DONNEES.md)
3. [Règles d'états UP / DOWN](docs/03_REGLES_ETATS.md)
4. [Connecteurs OMC](docs/04_CONNECTEURS_OMC.md)
5. [Installation et exploitation](docs/05_INSTALLATION_EXPLOITATION.md)
6. [Guide utilisateur](docs/06_GUIDE_UTILISATEUR.md)
7. [Tests et procédures de validation](docs/07_VALIDATION.md)
8. [Informations à fournir pour connecter les OMC réels](docs/08_INFORMATIONS_A_FOURNIR.md)
9. [Carte de l'Algérie et référentiel des 69 wilayas](docs/09_CARTOGRAPHIE.md)
10. [Intégration Prometheus / Alertmanager](docs/10_PROMETHEUS.md)
11. [Référentiel des sites (KMZ / Excel) et rapprochement avec les OMC](docs/11_REFERENTIEL.md)
12. [Exporteur d'OMC par fichiers pour Prometheus (node_exporter)](docs/12_EXPORTEUR_FICHIERS.md)
13. [Alarmes de l'OMC par traps SNMP (interface nord)](docs/13_ALARMES_SNMP.md)

Attributions des données cartographiques : voir [NOTICE.md](NOTICE.md).
