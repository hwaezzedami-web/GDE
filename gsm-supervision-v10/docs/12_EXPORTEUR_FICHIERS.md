# 12. Exporteur d'OMC par fichiers (node_exporter, collecteur textfile)

Chaîne complète, entièrement en lecture seule, sur le serveur de supervision :

```
OMC Huawei ──(export planifié : CSV)──▶ omc-exports/huawei/      (dépôt SFTP/FTP de l'OMC, ou tâche planifiée)
                                            │  lecture seule
                              omc-exporter-huawei  (script Python, sans réseau)
                                            │  écrit gsm_huawei.prom (écriture atomique)
                                    node-exporter  (collecteur textfile)
                                            │  :9100/metrics
                                       Prometheus  (job gsm-omc-textfile)
                                            │  PromQL
                                Application (source PROM-HUAWEI)
```

- **Rien n'est installé sur le serveur OMC** : on ne fait que lire les exports qu'il dépose.
- `node_exporter` publie aussi les métriques du serveur de supervision lui-même (CPU, mémoire, disques).
- Aucun format d'équipementier n'est supposé : la configuration (noms de colonnes, valeurs d'état,
  extraction du code site) est écrite à partir de l'**export réel**, avec l'outil d'inspection. Le script
  refuse de démarrer tant qu'une valeur `A_COMPLETER` subsiste.

## Mise en place (Huawei)

```bash
cd ~/gsm-supervision
./scripts/omc_exporter.sh huawei init                       # config/exporters/huawei.json + omc-exports/huawei/
# Faire déposer les exports de l'OMC dans omc-exports/huawei/ (voir « Arrivée des exports »)
./scripts/omc_exporter.sh huawei inspecter omc-exports/huawei/<export>.csv
nano config/exporters/huawei.json                           # remplacer les A_COMPLETER
./scripts/omc_exporter.sh huawei tester                     # affiche les métriques, n'écrit rien
./scripts/omc_exporter.sh huawei demarrer                   # node-exporter + exporteur, Prometheus rechargé
./scripts/omc_exporter.sh huawei etat                       # ce que Prometheus reçoit
```

`demarrer` ajoute `COMPOSE_PROFILES=huawei` dans `.env` : les commandes `docker compose up / down / ps`
habituelles incluent alors l'exporteur.

### Remplir la configuration

`inspecter` affiche chaque colonne de l'export avec ses valeurs les plus fréquentes. Renseigner :

| Clé | Contenu |
|---|---|
| `input.pattern` | nom des fichiers d'export (jokers `*`), le plus récent est lu |
| `input.max_age_s` | au-delà (30 min par défaut), l'export est jugé trop ancien : collecte en échec |
| `columns.ne_id` | colonne identifiant l'équipement (unique dans l'OMC) |
| `columns.status` | colonne de l'état (connexion / service) |
| `status_map` | **chaque** valeur d'état → `1` UP, `0` DOWN, `2` dégradé ; les autres valeurs sont ignorées et listées dans `gsm_exporter_unmapped_status` |
| `columns.site_id` **ou** `derive.site_id_regex` | code site Mobilis : colonne dédiée, ou extrait du nom du NE par une expression avec un groupe `(?P<site>…)` |
| `columns.technology` + `technology_map` **ou** `technology_default` | technologie (2G/3G/4G/5G ; GSM, UMTS, LTE, NR reconnus d'office) ; `technology_default` si un fichier ne concerne qu'une technologie |
| `filter` | facultatif : ne garder que certaines lignes (par exemple les seuls types de NE radio) |
| `min_elements` | en dessous, l'export est jugé incomplet : collecte en échec |

Le code site ainsi publié est rapproché du référentiel de l'application (zéros de tête, correspondances
de codes de l'écran « Sites inconnus »).

### Déclarer la source dans l'application

**Administration › Sources OMC** : modifier `PROM-HUAWEI` (ou la créer), connecteur « Prometheus /
Alertmanager », équipementier Huawei, péremption 900 s, configuration :

```json
{
  "url": "http://prometheus:9090",
  "health_query": "gsm_exporter_up{vendor=\"${vendor}\"} * on(vendor) ((time() - gsm_exporter_heartbeat_timestamp_seconds{vendor=\"${vendor}\"}) < bool 300)",
  "status": { "query": "gsm_ne_oper_status{vendor=\"${vendor}\", job=\"gsm-omc-textfile\"}" }
}
```

- `job="gsm-omc-textfile"` écarte les données **fictives** du `demo-exporter`. Une fois les vraies données
  validées, retirer le job `gsm-omc-huawei` de démonstration de `deploy/prometheus/prometheus.yml`.
- Avant d'activer la source :
  `docker compose exec collector python -m app.cli test-source PROM-HUAWEI` (rien n'est écrit en base).

## Fiabilité : jamais de fausse panne

| Situation | Effet dans Prometheus | Effet dans l'application |
|---|---|---|
| Export absent, illisible, colonne manquante, trop ancien, trop peu d'équipements | plus aucune série `gsm_ne_oper_status`, `gsm_exporter_up = 0`, `gsm_exporter_error{message}` | collecte en **ÉCHEC**, états vieillissants puis **INCONNU** |
| Script arrêté | `gsm_exporter_heartbeat_timestamp_seconds` vieillit | requête de santé à 0 : **ÉCHEC** |
| node_exporter arrêté | cible `gsm-omc-textfile` en échec, séries périmées | **ÉCHEC** |
| Valeur d'état inconnue | équipement ignoré, `gsm_exporter_unmapped_status{value}` | équipement absent de la collecte (à corriger dans `status_map`) |

Alertes Prometheus fournies (`deploy/prometheus/rules/gsm.rules.yml`) : `GsmExportOmcEnEchec`,
`GsmScriptExportArrete`.

## Arrivée des exports

L'exporteur lit un dossier local du serveur de supervision (`OMC_EXPORT_DIR`, par défaut
`./omc-exports/<vendor>/`). Selon ce que l'OMC permet (à confirmer avec l'équipe OSS) :

- l'OMC **dépose** ses exports planifiés par SFTP/FTP sur ce serveur, avec un compte dédié limité à ce dossier ;
- ou une **tâche planifiée** du serveur de supervision les récupère sur l'OMC avec un compte en lecture seule
  (`sftp`, `rsync` par SSH…), dans un fichier temporaire renommé en fin de copie : un fichier en cours de copie
  n'est jamais lu (`stable_s` : 30 s sans modification exigées).

Purger les anciens exports (par exemple au-delà de 7 jours) pour limiter l'espace disque :
`find omc-exports/huawei -type f -mtime +7 -delete`.

## Métriques publiées

| Métrique | Labels | Valeur |
|---|---|---|
| `gsm_ne_oper_status` | `vendor`, `site_id`, `ne_id`, `ne_name`, `ne_type`, `technology` | 1 UP, 0 DOWN, 2 dégradé |
| `gsm_exporter_up` | `vendor` | 1 lecture réussie |
| `gsm_exporter_heartbeat_timestamp_seconds` | `vendor` | dernier passage du script |
| `gsm_exporter_last_success_timestamp_seconds` | `vendor` | dernière lecture réussie |
| `gsm_exporter_source_mtime_seconds` | `vendor` | date de l'export lu |
| `gsm_exporter_rows` | `vendor`, `result` | lignes lues, exportées, ignorées (par motif) |
| `gsm_exporter_unmapped_status` | `vendor`, `value` | lignes dont l'état n'est pas dans `status_map` (20 valeurs max.) |
| `gsm_exporter_error` | `vendor`, `message` | 1 si la dernière lecture a échoué |

## Vérifié

- Tests automatisés : `backend/tests/test_textfile_exporter.py` (export de test fictif : conversion,
  doublons, code site absent, valeur d'état inconnue, export trop ancien ou absent, colonne erronée,
  configuration incomplète).
- Chaîne réelle `script → node_exporter 1.9.1 → Prometheus 3.11.0 → connecteur` : `test-source` correct
  (sites, technologies, UP / DOWN / DÉGRADÉ), puis export vieilli → collecte en ÉCHEC sans aucune bascule DOWN.
- Non vérifié : un export réel de l'OMC Huawei (à faire avec `inspecter` puis `tester`).
