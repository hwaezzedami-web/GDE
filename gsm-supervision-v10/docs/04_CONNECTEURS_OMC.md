# 4. Connecteurs OMC

## État d'avancement

| Connecteur | Statut | Commentaire |
|---|---|---|
| `prometheus` | **Fonctionnel, testé** contre Prometheus 3.11 et Alertmanager 0.31 réels (exporteur **fictif**) | États et alarmes depuis Prometheus / Alertmanager ; nécessite des exporteurs d'OMC — voir [10_PROMETHEUS.md](10_PROMETHEUS.md) |
| `file_export` (générique) | **Fonctionnel, testé** sur des fichiers d'export **fictifs** | Lit le dernier fichier CSV d'inventaire / d'états / d'alarmes, en répertoire local (monté) ou SFTP |
| `sql_readonly` (générique) | **Fonctionnel**, garde-fous testés | Requêtes `SELECT` fournies par l'exploitant, transaction lecture seule |
| `ericsson`, `huawei`, `zte` | **Ossature prête — NON opérationnels** | Délèguent à `file_export` ou `sql_readonly` selon l'interface réellement disponible ; profils à compléter (`A_COMPLETER`). L'option `api` (interface nord / NBI) n'est pas implémentée : à développer sur documentation officielle |
| `manual_csv` | Fonctionnel | Import CSV depuis l'interface ou la ligne de commande (pas de collecte automatique) |
| `demo` | Fonctionnel | Simulateur sur données **fictives** — ne jamais utiliser en production |

**Aucune intégration équipementier ne doit être déclarée opérationnelle** (case « Intégration validée » d'une source) avant la procédure de validation sur données réelles décrite dans [07_VALIDATION.md](07_VALIDATION.md).

## Architecture

Chaque connecteur implémente `BaseConnector.collect() -> CollectResult` ([`connectors/base.py`](../backend/app/collector/connectors/base.py)) et ne fait **que lire** : il n'écrit ni en base ni côté OMC. Le résultat est exprimé dans le modèle commun ([`collector/model.py`](../backend/app/collector/model.py)) :

- `NSite` : code site, nom, coordonnées, wilaya, commune, adresse, infos complémentaires ;
- `NElement` : identifiant d'équipement dans l'OMC, site, technologie, type, état normalisé, valeur brute, horodatages ;
- `NAlarm` : identifiant, site / équipement, code, description, gravité, début, fin ;
- `inventory_complete` / `alarms_complete` : si vrai, les équipements absents sont désactivés et les alarmes absentes terminées.

Un connecteur qui lève `ConnectorError(transient=True)` est relancé (attente exponentielle) ; `ConnectorNotConfigured` arrête immédiatement avec un message explicite. Une source en erreur n'affecte jamais les autres.

## Déclarer une source

**Administration › Sources OMC › Ajouter une source** (ou `POST /api/admin/omc-sources`) :

| Champ | Exemple |
|---|---|
| Code | `HUAWEI-OMC-CENTRE` (majuscules, chiffres, `-`, `_`) |
| Équipementier | HUAWEI |
| Connecteur | `huawei` |
| Fréquence | 300 s |
| Péremption | 1 200 s (3 à 4 × la fréquence) |
| Configuration | JSON fusionné **par-dessus** le profil `profiles/huawei.yaml` |

Les **secrets** ne sont jamais saisis dans l'interface : ils sont lus par le service de collecte dans des variables d'environnement (`.env.omc` en Docker, `/etc/gsm-supervision/omc.env` hors Docker) :

```
OMC_HUAWEI_OMC_CENTRE_USERNAME=…
OMC_HUAWEI_OMC_CENTRE_PASSWORD=…           # ou PRIVATE_KEY_PATH / PRIVATE_KEY_PASSPHRASE
OMC_HUAWEI_OMC_CENTRE_DSN=…                # connecteur SQL
OMC_HUAWEI_OMC_CENTRE_PASSWORD_FILE=/run/secrets/…   # variante fichier
```

L'API refuse toute configuration contenant une clé ressemblant à un secret (`password`, `token`, `key`…).

## Configuration `file_export`

Exemple complet (format **fictif**, celui des tests `backend/tests/fixtures/file_export/`) :

```json
{
  "interface": "file_export",
  "transport": "sftp",
  "sftp": { "host": "10.x.x.x", "port": 22, "remote_dir": "/export/inventaire",
            "known_hosts_file": "/app/config/known_hosts", "timeout_s": 30 },
  "files": {
    "inventory": { "pattern": "inventaire_*.csv" },
    "status":    { "pattern": "etat_*.csv" },
    "alarms":    { "pattern": "alarmes_*.csv", "required": false }
  },
  "csv": { "delimiter": ";", "encoding": "utf-8-sig", "skip_rows": 0 },
  "max_file_age_s": 3600,
  "columns": {
    "inventory": { "site_id": null, "site_name": null, "technology": null,
                   "element_id": "NOM_EQUIPEMENT", "element_name": "LIBELLE",
                   "latitude": "LAT", "longitude": "LON", "element_type": "TYPE_EQ",
                   "wilaya_code": "WILAYA_NO", "commune": "COMMUNE" },
    "status": { "element_id": "NOM_EQUIPEMENT", "status": "ETAT_CNX", "observed_at": "HORODATAGE" },
    "alarms": { "alarm_id": "ID_ALARME", "element_id": "NOM_EQUIPEMENT", "code": "CODE",
                "description": "TEXTE", "severity": "NIVEAU", "raised_at": "DEBUT" }
  },
  "derive": { "site_id_regex": "^(?P<site>TST_\\d{4})_" },
  "value_maps": {
    "status": { "CONNECTE": "UP", "DECONNECTE": "DOWN" },
    "severity": { "NIV1": "CRITICAL", "NIV2": "MAJOR", "NIV3": "MINOR" },
    "element_type_technology": { "TYPE_A": "2G", "TYPE_B": "3G", "TYPE_C": "4G" }
  },
  "timestamps": { "format": "%Y-%m-%d %H:%M:%S", "timezone": "Africa/Algiers" },
  "extra_columns": ["ZONE_TEST"],
  "inventory_complete": true,
  "alarms_complete": true
}
```

Points importants :
- **Mettre à `null`** les champs de colonnes sans objet (sinon la valeur `A_COMPLETER` du profil bloque l'exécution).
- `known_hosts_file` est obligatoire en SFTP (`ssh-keyscan -H <hôte> > config/known_hosts`, empreinte à vérifier avec l'équipe OMC) : un serveur inconnu est refusé.
- Le répertoire local `/data/omc` du conteneur correspond à `OMC_EXPORT_DIR` sur l'hôte, monté **en lecture seule**.
- Sans colonne d'horodatage, l'observation est datée de la modification du fichier.
- Si les coordonnées GPS ne sont pas dans l'OMC, prévoir une source dédiée (export de la base de planification radio) ou un import CSV du référentiel de sites : l'inventaire est fusionné par code site.

## Configuration `sql_readonly`

```json
{
  "interface": "sql_readonly",
  "dsn_secret": "DSN",
  "statement_timeout_s": 120,
  "queries": {
    "inventory": "SELECT … AS site_code, … AS ne_name, … AS rat FROM …",
    "status":    "SELECT … FROM …"
  },
  "columns": { "inventory": { "site_id": "site_code", "element_id": "ne_name", "technology": "rat" },
               "status": { "element_id": "ne_name", "status": "etat" } },
  "value_maps": { "status": { "…": "UP" } }
}
```

Uniquement si un accès SQL est **documenté et autorisé** par l'équipementier / l'exploitant, avec un compte dédié en lecture seule (idéalement sur une vue ou une réplique). Le pilote Python du SGBD doit être ajouté à `requirements.txt` s'il ne s'agit pas de PostgreSQL.

## Tester une source sans rien écrire

```bash
docker compose exec collector python -m app.cli test-source HUAWEI-OMC-CENTRE
```

Affiche le nombre de sites / équipements / alarmes lus, les lignes rejetées avec leur motif, la répartition des états, et un échantillon `valeur brute -> état normalisé`. Puis, collecte réelle : bouton **Synchroniser** ou `python -m app.cli run-source CODE`. Les résultats sont visibles dans **Administration › Collectes**.

## Ajouter un nouveau type de connecteur (ex. API NBI)

1. Créer `backend/app/collector/connectors/<nom>.py`, classe dérivée de `BaseConnector`, méthode `collect()` renvoyant un `CollectResult` ; lever `ConnectorError` / `ConnectorNotConfigured`.
2. L'enregistrer dans `collector/registry.py` et dans la contrainte `omc_sources.connector_type` (script SQL d'évolution).
3. Ajouter des tests sur des réponses enregistrées et anonymisées.
4. Valider en lecture seule sur l'environnement réel (07_VALIDATION.md) avant de cocher « Intégration validée ».
