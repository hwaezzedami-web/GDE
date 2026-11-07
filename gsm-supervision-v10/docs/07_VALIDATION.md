# 7. Tests et procédures de validation

## Tests automatisés (backend)

Exécutés sur une **vraie base PostgreSQL 16 + PostGIS 3.4** (base temporaire créée puis supprimée) :

```bash
cd backend
pip install -r requirements-dev.txt
TEST_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/postgres pytest -q
```

Résultat de référence lors de la livraison : **63 tests réussis** (dont 12 pour le référentiel de sites et sa gestion : création, modification, retrait, rattachement des codes OMC : lecture KMZ/Excel/CSV, rejet des DTD, corrections, différentiel, garde-fou de synchronisation, rapprochement OMC et zéros de tête, anomalies, dossier surveillé), dont le test d'intégration contre un Prometheus 3.11.0 et un Alertmanager 0.31.1 réels (Python 3.13, versions figées dans `requirements.txt`).

| Fichier | Couvre |
|---|---|
| `test_status_engine.py` | Consolidation des états (tout UP, tout DOWN, partiel, périmé, inconnu, multi-équipementiers), règles d'alarmes validées / autres équipementiers, alarme majeure, anti-rebond (attente, confirmation, annulation, horodatage à la 1re détection) |
| `test_connectors_ingest.py` | Connecteur `file_export` sur exports fictifs (mapping colonnes, valeurs, fuseau horaire Algérie → UTC, dérivation du code site, rejets motivés) ; refus des profils `A_COMPLETER` et du mauvais équipementier ; fichier d'export trop ancien ; **idempotence** (pas de doublon ni de transition parasite en rejouant une collecte) ; historisation équipement + site ; inventaire / alarmes complets (désactivation, fin d'alarme) ; coordonnées hors Algérie ; **coupure OMC ⇒ FAILED, sites inchangés puis UNKNOWN, jamais DOWN** ; nouvelles tentatives ; jeu fictif + simulateur |
| `test_api.py` | Authentification obligatoire, verrouillage et audit des échecs, révocation à la déconnexion, rôles, changement de mot de passe imposé, **cohérence carte / tableau / compteurs sous 7 combinaisons de filtres**, fiche et historique, pannes et disponibilité, exports Excel/CSV et leur journalisation, validation des paramètres, règles d'alarmes, refus des secrets dans la configuration d'une source, référentiels |
| `test_prometheus.py` | Connecteur Prometheus : contrat de métriques, filtrage par équipementier, état par valeur ou par label, `NaN`, exporteur arrêté (`up == 0`) ⇒ échec et non panne, erreurs PromQL / 401 / injoignable, alarmes Alertmanager et PromQL, préservation du référentiel ; intégration réelle (si `PROMETHEUS_TEST_URL`) |
| `test_geo.py` | Référentiel des 69 wilayas et contours embarqués (chaque chef-lieu dans sa wilaya), rattachement automatique des sites, recalcul après la réforme (ex. Laghouat → Aflou), contours officiels personnalisés jamais écrasés |
| `test_schema.py` | Alignement modèles ORM ↔ schéma SQL |

Vérifications complémentaires effectuées : compilation de l'interface (`npm run build`), parcours de l'interface dans un navigateur sans tête sur 3 000 sites fictifs (carte, fiche, historique, tableau de bord, administration, alarmes, affichage mobile — captures dans `docs/screenshots/`), sauvegarde puis restauration dans une base vierge, validation syntaxique de `docker-compose.yml`. Les images Docker n'ont pas pu être construites dans l'environnement de développement (pas de démon Docker) : **à construire et vérifier lors de l'installation** (étape 1 ci-dessous).

## Recette du socle (avant raccordement des OMC)

| # | Vérification | Attendu |
|---|---|---|
| 1 | `docker compose up -d --build` puis `docker compose ps` | 4 services démarrés, `db` et `api` « healthy » |
| 2 | `curl http://<serveur>:8080/api/health` | `{"status":"ok","database":"ok"}` |
| 3 | Connexion avec l'administrateur initial | Changement de mot de passe imposé |
| 4 | `seed-demo`, puis carte | ~3 000 sites fictifs, groupes colorés, compteurs cohérents |
| 5 | Filtre « Sites DOWN uniquement » | Carte, compteurs et tableau affichent le même nombre |
| 6 | Clic sur une ligne du tableau | Carte centrée sur le site, fiche ouverte |
| 7 | Attendre 2 à 3 minutes | Nouvelles pannes fictives dans « Dernières pannes » et l'historique |
| 8 | Arrêter le collecteur (`docker compose stop collector`) 35 minutes | Bandeau rouge « service de collecte ne répond plus » ; sites passent INCONNU (réévaluation de secours par l’API), aucun DOWN ajouté |
| 9 | Compte Consultation sans droit d'export | Boutons d'export absents, API refuse (403) |
| 10 | 5 mauvais mots de passe | Compte verrouillé, événements dans l'audit |
| 11 | Export Excel avec filtres | Fichier conforme aux filtres, entrée dans l'audit |
| 12 | Sauvegarde + restauration sur un serveur de test | Données identiques |

## Validation d'une intégration OMC réelle (par source)

À dérouler **pour chaque OMC** avant de cocher « Intégration validée sur données réelles ».

1. **Préparation** : compte lecture seule créé, flux réseau ouverts, secrets dans `.env.omc`, empreinte SFTP vérifiée, profil complété (aucune valeur `A_COMPLETER`).
2. **Lecture à blanc** : `python -m app.cli test-source <CODE>` — aucun rejet inexpliqué ; toutes les valeurs brutes d'état reconnues (sinon compléter `value_maps.status`).
3. **Contrôle d'inventaire** : comparer le nombre de sites et d'équipements par technologie avec un décompte de référence fourni par l'équipe OMC (écart expliqué).
4. **Contrôle des coordonnées** : échantillon de 20 sites répartis sur plusieurs wilayas comparé au référentiel de planification ; aucun site hors de sa wilaya.
5. **Contrôle des états** : pour 10 sites UP et tous les sites signalés hors service au moment du test, comparer avec la console OMC. Taux de concordance attendu : 100 % (écarts analysés et corrigés dans `value_maps`).
6. **Cas de panne réelle ou provoquée en maintenance** : le passage DOWN puis le retour UP apparaissent dans l'historique avec des horodatages cohérents (± fréquence de collecte).
7. **Coupure de la collecte** (désactiver le compte ou le flux quelques minutes) : collecte FAILED, aucune bascule DOWN, retour à la normale ensuite.
8. **Alarmes** (si collectées) : alarmes actives cohérentes avec la console ; fin d'alarme reflétée.
9. **Règles d'alarmes** : chaque règle saisie justifiée (note), validée par un administrateur.
10. **Charge** : durée de collecte (Administration › Collectes) nettement inférieure à la fréquence choisie.
11. Consigner les résultats (date, version OMC, écarts, validateur) ; cocher « Intégration validée ».
