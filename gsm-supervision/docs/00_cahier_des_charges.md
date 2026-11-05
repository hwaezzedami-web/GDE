# Supervision GSM Algérie : résumé du projet pour le recréer avec Claude Code

> Mode d'emploi : ouvrir Claude Code dans un dossier vide et lui donner ce fichier en disant :
> « Lis ce cahier des charges et construis le projet phase par phase. À la fin de chaque phase, lance les
> tests et attends ma validation avant de passer à la suivante. »
> Langue du projet : **français** (interface, messages, documentation, commentaires).

---

## 1. Objectif

Application web de **supervision géographique des sites radio 2G/3G/4G/5G** de Mobilis (Algérie) :
- une carte de l'Algérie (69 wilayas, utilisable **hors ligne**) qui montre l'état de chaque site
  (pylônes « 3D ») ;
- les états UP / DOWN / DÉGRADÉ / INCONNU / NON SUPERVISÉ ;
- l'historique des pannes, les alarmes, le tableau de bord (disponibilité, tendances) et les exports ;
- le **référentiel des sites**, importé depuis KMZ/KML/Excel/CSV/GeoJSON, avec détection des écarts
  avec les OMC ;
- la collecte en **lecture seule** depuis les OMC Ericsson, Huawei et ZTE, via Prometheus, des fichiers
  d'export ou les traps SNMP de l'interface nord.

## 2. Contraintes non négociables

1. **Ne jamais inventer** d'API, de commande OMC, d'OID SNMP ni de format d'export d'équipementier.
   - Les profils et configurations gardent des valeurs `A_COMPLETER`, qui **bloquent l'exécution** tant
     qu'elles ne sont pas remplies à partir de données réelles.
2. Une intégration n'est déclarée opérationnelle qu'après un test sur des **données réelles**.
3. **Aucun secret dans le code source.**
   - Secrets dans `.env` et `.env.omc` (non versionnés), sous la forme `OMC_<CODE>_*` ; les variantes
     `*_FILE` sont acceptées pour les secrets Docker.
   - L'API d'administration refuse toute clé « secrète » dans la configuration JSON d'une source.
4. Accès aux OMC **strictement en lecture**.
   - Aucune modification de configuration des équipements.
   - **Rien à installer sur les serveurs OMC.**
   - Les OMC ne sont jamais exposés sur Internet.
5. **Perte de collecte ≠ panne radio.**
   - Une collecte en échec ou des données périmées donnent l'état **INCONNU**, jamais DOWN.
   - Un test dédié vérifie ce point (`test_omc_outage_is_not_a_radio_outage`).
6. Les données réelles de l'opérateur (KMZ, exports) ne vont **jamais** dans le dépôt, les tests ni la
   documentation.
   - `.gitignore` : `referentiel-depot/*`, `*.kmz`, `config/exporters/*.json`, `.env`, `.env.omc`.
   - Les données de test sont **fictives** (générateur fourni).

## 3. Pile technique

| Couche | Choix |
|---|---|
| Base | PostgreSQL 16 + PostGIS 3.4 + pg_trgm |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.1, psycopg 3, Pydantic, APScheduler (collecteur), defusedxml (KML), openpyxl |
| Frontend | React 18 + Vite, Leaflet + leaflet.markercluster (rendu **canevas**), Recharts, react-router |
| Supervision | Prometheus 3, Alertmanager, node_exporter 1.9.1 (collecteur textfile), Net-SNMP `snmptrapd` |
| Déploiement | Docker Compose (db, api, collector, web/nginx), fichier optionnel `docker-compose.prometheus.yml` avec profils |

## 4. Arborescence cible

```
backend/app/
  main.py config.py db.py deps.py security.py models.py filters.py cli.py logging_setup.py
  api/        auth sites dashboard alarms export reference site_reference site_management admin
  services/   status_engine ingest settings_service geo csv_import bootstrap
  reference/  parsers mapping service anomalies manage watch
  collector/  runner registry mapping normalize model secrets
              connectors/ base prometheus file_export sql_readonly vendor demo
              profiles/   ericsson.yaml huawei.yaml zte.yaml prometheus.yaml   (A_COMPLETER)
              transports/ files
backend/tests/
db/init/      01_extensions 02_schema 03_reference_wilayas 04_wilaya_boundaries 05_site_reference 06_site_management
db/reference/ wilayas.csv wilaya_boundaries.geojson
frontend/src/ components/ lib/ pages/
tools/        demo_exporter/ omc_textfile_exporter/ snmp_trap_receiver/
scripts/      omc_exporter.sh snmp_alarms.sh prometheus_password.sh build_basemap.mjs build_wilaya_reference.py
deploy/       nginx/ prometheus/(prometheus.yml, rules/gsm.rules.yml, alertmanager.yml) systemd/ scripts/(backup, restore)
docs/         01..13
data/test/    generate_test_data.py sites_fictifs.csv
referentiel-depot/  omc-exports/  config/exporters/
```

## 5. Modèle de données (`db/init/*.sql` = source de vérité)

**Règles générales**
- Les scripts SQL sont **idempotents** (`IF NOT EXISTS`, `ON CONFLICT`) et rejoués à chaque démarrage par
  `python -m app.cli init-db`.
- Chaque colonne est mappée dans `models.py` ; `test_schema.py` échoue si une colonne n'est pas mappée.
- `schema_version` = 4.

**Tables**

| Table | Contenu clé |
|---|---|
| `wilayas` | les 69 wilayas (code, nom FR/AR, région/DR), contour PostGIS |
| `omc_sources` | code, équipementier, connecteur, `config` JSONB, `value_maps`, `stale_after_s`, intervalle, `last_status` |
| `sites` | `external_id` (code site), nom, géométrie, wilaya, commune, adresse, équipementier, `display_status` ; champs référentiel : `in_reference`, `ref_status` (IN_SERVICE / TEMP_OFF / PLANNED / REMOVED / OTHER), `ref_source` (IMPORT/MANUAL), `ref_updated_at/by`, `is_supervised`, `last_supervised_at`, `extra` JSONB |
| `site_elements` | NE par site : technologie, `oper_status`, `raw_status`, `observed_at`, source |
| `status_history` | transitions site/élément : ancien et nouvel état, date, source, motif |
| `alarms` | alarmes actives et terminées (id OMC, code, gravité, description, site, NE) |
| `alarm_rules` | règles alarme → DOWN/DEGRADED (portée site ou élément) ; **actives seulement si validées** par un admin |
| `app_settings` | paramètres JSON (`status_rules`, `reference`…) |
| `collection_runs` | journal des collectes (OK / FAILED, compteurs, erreurs) |
| `kpi_snapshots`, `service_heartbeats` | tendances, santé des services |
| `users` | rôles ADMIN / SUPERVISOR / VIEWER, `can_export`, verrouillage après échecs, changement de mot de passe imposé |
| `audit_log` | toute action sensible |
| `reference_imports` | historique des imports du référentiel (différentiel, auteur, fichier) |
| `site_anomalies` | UNKNOWN_SITE, REMOVED_BUT_ACTIVE, PLANNED_BUT_ACTIVE, SUPERVISION_LOST, NEVER_SUPERVISED ; ack/reopen |
| `site_code_aliases` | code OMC → code référentiel (FK `sites(external_id)` ON UPDATE/DELETE CASCADE) |

## 6. Moteur d'états (`services/status_engine.py`)

Le moteur est une **fonction pure** (testée seule) plus une orchestration.

**Calcul**
1. L'état d'un élément vient de l'OMC, traduit par `value_maps.status`. Une valeur inconnue donne
   UNKNOWN avec un avertissement ; la valeur brute est conservée.
2. **Péremption** : si l'observation date de plus de `stale_after_s` (défaut 1 800 s), l'état devient
   UNKNOWN.
3. Les **règles d'alarmes validées** peuvent forcer DOWN ou DEGRADED.
4. **Consolidation par site**
   - Aucun état connu : UNKNOWN.
   - Tous les éléments DOWN : DOWN.
   - Une partie DOWN ou DEGRADED : DEGRADED (paramètre `partial_down_is_degraded`).
   - Tous UP avec une alarme CRITICAL ou MAJOR : DEGRADED (paramètre `major_alarm_degrades`).
   - Sinon : UP.
   - `unknown_elements_policy` vaut `ignore` ou `degrade`.
5. **Anti-rebond** : `down_confirm_s` / `up_confirm_s`. La transition est horodatée à la **première
   détection**.
6. **Historisation** de toutes les transitions.

**Affichage et calculs dérivés**
- **NON SUPERVISÉ** : `display_status = UNSUPERVISED` si `in_reference AND NOT is_supervised`.
  Message : « Non supervisé : aucun OMC ne remonte ce site ».
- **Périmètre par défaut** : les sites PLANNED ou REMOVED non supervisés sont masqués.
- **Disponibilité** = 1 − DOWN / (observé − UNKNOWN).
- Les paramètres sont modifiables dans Administration › Règles d'états, avec des bornes, une entrée
  d'audit et une réévaluation immédiate.

## 7. Ingestion et rapprochement des codes (`services/ingest.py`)

- Upserts sans doublon ; l'horodatage d'observation est la date du fichier, pas l'heure de lecture.
- `canonical_site_codes()` résout les codes dans cet ordre : **alias explicites** (`site_code_aliases`),
  puis **zéros de tête** (si la correspondance est unique).
- Pour un site du référentiel, les champs du référentiel (nom, position, wilaya, commune, adresse)
  **priment** sur l'OMC. Le nom OMC est gardé dans `extra.omc_name`.
- Un site du référentiel n'est jamais désactivé par une collecte.
- Un site inconnu remonté par un OMC est créé hors référentiel et apparaît dans « Sites inconnus ».

## 8. Référentiel des sites (`reference/`)

- **Parsers** : KMZ, KML (defusedxml), XLSX, CSV et GeoJSON. Détection automatique des colonnes, avec un
  mapping configurable (`wilaya_from`, code, nom, lat/lon, statut, technologies, DR).
- **Import en deux temps**
  - `preview` calcule un différentiel (ajouts, modifications, retraits) et signale les modifications
    manuelles qui seraient écrasées.
  - `apply` est protégé par l'advisory lock **7421004** et écrit `ref_source = IMPORT`.
- **Dépôt automatique** : le dossier `referentiel-depot/` est surveillé (watch job). Commande CLI :
  `reference-import fichier.kmz --dry-run`.
- **Rapprochement** : advisory lock **7421003**, lancé après chaque collecte et toutes les 300 s.
  - Il produit les anomalies listées au §5.
  - Les suggestions de code passent par trigramme (`similarity ≥ 0.5`).
- **Gestion manuelle** (`manage.py`)
  - Créer un site (adopte un site inconnu existant), le modifier.
  - Retirer ou supprimer en lot. La purge est refusée s'il reste des éléments actifs.
  - **Rattacher un site inconnu** : ses éléments, alarmes et historique sont déplacés, un alias est créé,
    puis la source est supprimée.
  - Supprimer un alias.
- Validé sur le vrai KMZ Mobilis : 18 258 sites importés en environ 7 s, rapprochement en 0,05 s.
  Attention : le fichier découpe en 58 wilayas, l'application en 69 (`wilaya_from`).

## 9. API REST (préfixe `/api`, JWT, documentation `/api/docs`)

| Module | Routes |
|---|---|
| auth | `POST /login`, `GET /me`, `POST /logout`, `POST /change-password` |
| sites | `GET /map` (points légers), `GET ""` (tableau paginé), `GET /{id}`, `GET /{id}/history` |
| dashboard | `/summary`, `/trend`, `/outages`, `/availability` |
| alarms | `GET ""` |
| export | `/sites`, `/outages`, `/alarms` (CSV/XLSX, limite `EXPORT_MAX_ROWS`, droit `can_export`) |
| reference | `GET ""` (wilayas), `/communes`, `/wilaya-boundaries` |
| site-reference | `/summary`, `/anomalies/count`, `/import/preview`, `/import/apply`, `/imports`, `/anomalies`, `/anomalies/{id}/ack\|reopen`, `/reconcile`, `/anomalies/export`, `/export`, `/template` |
| site-management | `/options`, `/sites` (GET/POST/PUT, `POST /sites/delete`), `/sites/export`, `/unknown-sites` (+ `/export`, `/{id}/link`, `/ack`), `/aliases` (GET, DELETE `/{omc_code}`) |
| admin | `/users`, `/settings/{key}`, `/alarm-rules` (+ `/validate`), `/omc-sources` (+ `/sync`), `/collection-runs`, `/import/sites-csv`, `/audit` |

**Filtres communs** (`filters.py`, `SiteFilters.where()`)
- Utilisés à l'identique par la carte, le tableau, le tableau de bord et les exports.
- Critères : état, technologie, équipementier (UNKNOWN compris), wilaya, DR, `ref` (IN_SERVICE / TEMP_OFF /
  PLANNED / REMOVED / OTHER / NONE / ALL), supervisé, recherche texte.

**Sécurité**
- Mots de passe bcrypt ; verrouillage après `LOGIN_MAX_FAILURES` échecs.
- Rôles : VIEWER en lecture ; SUPERVISOR pour les acquittements et les exports ; ADMIN pour le reste.
- Requêtes SQL toujours avec paramètres liés.
- Audit de toutes les actions sensibles.

## 10. Collecteur (`collector/`)

- Service séparé (APScheduler), une tâche par source active, avec reprise sur erreur et journal dans
  `collection_runs`.
- **Connecteurs**
  - `prometheus` : requêtes PromQL configurables (`status.query`, `alarms` avec `source: promql`,
    `health_query`, `min_series`). Le libellé `job="gsm-omc-textfile"` écarte la démo.
  - `file_export` : CSV local ou SFTP, `max_file_age_s`, fichier stable avant lecture.
  - `sql_readonly`.
  - `vendor` (profils YAML `A_COMPLETER`).
  - `demo` (données fictives).
- CLI `test-source <CODE>` : teste une source **sans rien écrire** en base.

## 11. Frontend (React)

**Pages**
- Carte : clusters ; marqueurs **pylône 3D** (`towerMarker.js`, qui étend `L.CircleMarker`, avec sprites
  canevas en cache et taille selon le zoom de 0,6 à 1,8) ; fond hors ligne ; contours des wilayas ;
  bandeau en cas de collecte en échec.
- Fiche site : éléments, alarmes, historique, section référentiel, anomalies.
- Tableau des sites : colonnes DR et référentiel.
- Tableau de bord : KPI, dont NON SUPERVISÉ ; cartes par DR ; tendances ; disponibilité.
- Alarmes.
- **Référentiel**, avec ses onglets dans l'URL : résumé, sites, inconnus, anomalies, import, imports,
  paramètres. Badge d'anomalies dans le menu.
- **Gestion des sites** (`SitesManager.jsx`) : lister, ajouter, modifier, retirer ou supprimer en lot.
  Formulaire `SiteFormDialog.jsx` avec un sélecteur de position sur carte (épingle en divIcon CSS, sites
  voisins affichés dès le zoom 11) et le motif de code `[A-Za-z0-9][A-Za-z0-9_.\/\-]*`.
- **Sites inconnus** (`UnknownSites.jsx`) : rattacher, ajouter au référentiel, ignorer ; correspondances
  de codes.
- Administration : utilisateurs, sources OMC, règles d'états, règles d'alarmes, audit.

**Accessibilité**
- Modales natives `<dialog>` + `showModal()` (`Dialog.jsx`, `ConfirmDialog`), avec repli pour `closedby`
  et `overscroll-behavior`.
- `fieldset`/`legend` et attributs `aria-*`.
- Affichage mobile correct.

## 12. Chaînes Prometheus

**Contrat de métriques**
- `gsm_ne_oper_status{vendor,site_id,ne_id,ne_name,ne_type,technology}` : 1 = UP, 0 = DOWN, 2 = dégradé.
- `gsm_ne_active_alarm{vendor,alarm_id,ne_id,site_id,code,severity,description}`.

### 12.1 Exporteur par fichiers (`tools/omc_textfile_exporter/`)

- Chaîne : export CSV de l'OMC → script Python **sans réseau** → fichier `.prom` (écriture atomique) →
  node_exporter textfile → Prometheus (job `gsm-omc-textfile`).
- Métriques de santé : `gsm_exporter_up`, `gsm_exporter_heartbeat_timestamp_seconds`,
  `gsm_exporter_last_success_timestamp_seconds`, `gsm_exporter_source_mtime_seconds`, `gsm_exporter_rows`,
  `gsm_exporter_unmapped_status`, `gsm_exporter_error`.
- Options `--inspect`, `--dry-run`, `--once`. La configuration `huawei.example.json` contient
  `A_COMPLETER`.
- Script `scripts/omc_exporter.sh huawei init|inspecter|tester|demarrer|etat|arreter`.
- `health_query` de la source :
  `gsm_exporter_up{vendor="${vendor}"} * on(vendor) ((time() - gsm_exporter_heartbeat_timestamp_seconds{vendor="${vendor}"}) < bool 300)`

### 12.2 Alarmes par traps SNMP (`tools/snmp_trap_receiver/`)

**Réception**
- Conteneur Debian bookworm avec `snmptrapd` (Net-SNMP 5.9) lancé en `-m "" -Onx`, écoute interne
  `udp:1162` publiée sur 162.
- `entrypoint.sh` génère la configuration à partir de `.env.omc` :
  - v2c (communauté) ou v3 authPriv ;
  - **Inform v3** : simple `createUser`, sans engine ID ;
  - **Trap v3** : `createUser -e ENGINE_ID`.
- `trap_handler.py` (traphandle) enregistre les traps **bruts** en JSON lignes dans
  `/data/spool/traps-AAAAMMJJ.jsonl`.
  - Verrou `flock` à l'écriture.
  - Valeurs hexadécimales décodées en UTF-8, puis GBK, puis Latin-1 ; une valeur longue peut continuer
    sur les lignes suivantes.
  - Filtre `SNMP_ALLOWED_SOURCES`, la boucle locale étant toujours acceptée.

**Traitement**
- `alarm_exporter.py` (AlarmBook) gère apparition, disparition, ignorés et inconnus.
- État persistant, avec reprise par offsets et `expire_after_days`.
- Écrit `gsm_ne_active_alarm` et les métriques `gsm_alarm_receiver_*` (heartbeat, traps, active,
  unknown_trap).
- `huawei_snmp.example.json` (`A_COMPLETER`) :
  - `event.by` (trap_oid ou varbind), `event.raise` / `clear` / `ignore` ;
  - `fields` : alarm_id, name, code, severity, ne_name, location, occurred ;
  - `severity_map`, `site_id.regex` / `from`, `timezone`.

**Exploitation**
- Script `scripts/snmp_alarms.sh huawei init|recevoir|test-local|inspecter|tester|activer|etat|arreter`.
  Le test local utilise l'OID fictif `.1.3.6.1.4.1.99999`.
- Services Compose : `snmp-trap-huawei` et `omc-alarms-huawei` (sans réseau, `user 0:0`), profil
  `huawei-snmp`, volume `snmp-huawei`.
- Source dans l'application (`PROM-HUAWEI-ALARMES`) : `min_series: 0` et `health_query` sur le heartbeat
  du récepteur (`< bool 120`).
- Règles Prometheus : `GsmExportOmcEnEchec`, `GsmScriptExportArrete`, `GsmRecepteurAlarmesArrete`.

## 13. Déploiement

- `docker compose up -d --build` avec les services `db`, `api`, `collector` et `web` (nginx).
- Réseaux `internal` et `omc`. Volumes `pgdata` et `logs`.
- Le fichier optionnel `docker-compose.prometheus.yml` ajoute `prometheus`, `alertmanager`,
  `demo-exporter`, `node-exporter`, `omc-exporter-huawei`, `snmp-trap-huawei` et `omc-alarms-huawei`.
- `.env` minimal :
  - `POSTGRES_PASSWORD`, `JWT_SECRET` (32 caractères ou plus ; l'API refuse de démarrer sans) ;
  - `INITIAL_ADMIN_PASSWORD` ;
  - `COMPOSE_FILE=docker-compose.yml:docker-compose.prometheus.yml` ;
  - `COMPOSE_PROFILES=huawei-snmp` (ajouter `,huawei` pour l'exporteur par fichiers) ;
  - `HUAWEI_SNMP_SOURCES=<IP du MAE>`.
- nginx : `client_max_body_size 60m` sur `/api/site-reference/import/`. Prometheus est accessible derrière
  `/prometheus/` avec authentification (`scripts/prometheus_password.sh`).
- Sauvegarde et restauration : `deploy/scripts/backup.sh` et `restore.sh`.
- **Ne jamais lancer `docker compose down -v`** : cela supprime la base.

## 14. Tests attendus

- Les tests tournent sur une vraie base PostgreSQL + PostGIS : une base `gsm_test_<pid>` est créée puis
  supprimée.
- Référence : **63 tests réussis, 1 ignoré**. Le test d'intégration Prometheus n'est activé que si
  `PROMETHEUS_TEST_URL` est défini.
- Fichiers : `test_status_engine`, `test_connectors_ingest`, `test_api`, `test_config`, `test_geo`,
  `test_prometheus`, `test_reference`, `test_schema`, `test_site_management`, `test_textfile_exporter`,
  `test_snmp_alarms`, plus `tests_e2e/smoke.py`.
- Toujours vérifier que l'interface compile avec `npm run build`.

## 15. Ordre de construction conseillé (une phase = tests verts + validation)

1. Socle : Docker Compose, schéma SQL, wilayas et contours, modèles, CLI `init-db`, authentification et
   utilisateurs, audit.
2. Moteur d'états, ingestion, connecteur `demo`, données fictives (`seed-demo`).
3. API sites, carte, tableau de bord, exports ; filtres communs.
4. Frontend : carte avec pylônes 3D, fiches, tableau, tableau de bord, alarmes, administration.
5. Collecteur et connecteurs `prometheus` et `file_export`, profils `A_COMPLETER`, `test-source`.
6. Référentiel : parsers, import en deux temps, rapprochement, anomalies.
7. Gestion des sites, sites inconnus, correspondances de codes, modales accessibles.
8. Pile Prometheus et exporteur par fichiers (node_exporter).
9. Récepteur de traps SNMP et AlarmBook.
10. Documentation `docs/01..13` et `CLAUDE.md`.

## 16. État réel et prochaines étapes (5 novembre 2026)

**Fait sur le serveur Docker1** (172.22.8.10, Ubuntu 24.04, `/home/oss/gsm-supervision`)
- Application déployée avec le référentiel Mobilis importé.
- Récepteur SNMP Huawei en écoute sur UDP 162 (Inform SNMPv3 authPriv, MD5/AES) ; `test-local` validé.

**À faire**
1. Sur le MAE (iMaster MAE-Access, 10.42.223.7), déclarer la destination Inform `172.22.8.10:162`, puis
   vérifier l'arrivée des traps avec `tcpdump -ni any udp port 162`.
2. Lancer `snmp_alarms.sh huawei inspecter` sur les vrais traps, puis remplir
   `config/exporters/huawei_snmp.json` avec les OID réels et la MIB de l'interface nord.
   - Avec CsnType = 0, le CSN sert d'identifiant d'alarme.
   - Placer le trap de test et le heartbeat dans `ignore`.
   - Enchaîner `tester` → `activer` → source `PROM-HUAWEI-ALARMES`.
3. Faire valider par l'équipe RAN les règles d'états (NodeB Unavailable et OML Fault → DOWN ?).
4. Obtenir un export d'état des NE Huawei pour l'exporteur par fichiers.
5. Ericsson et ZTE : pas commencés.
6. Pistes : alertes e-mail / SMS / Telegram, HTTPS + LDAP, sauvegardes automatiques, rapports.
