# 13. Alarmes de l'OMC par traps SNMP (interface nord)

L'OMC (ici iMaster MAE) **envoie** ses alarmes en temps réel, par traps SNMP, au serveur de supervision.
Rien n'est installé sur l'OMC : l'administrateur OSS y déclare seulement ce serveur comme destination des traps.

```
iMaster MAE ──(traps SNMP v3/v2c, UDP 162)──▶ snmp-trap-huawei   (snmptrapd : traps enregistrés BRUTS)
                                                     │ volume snmp-huawei (dossier d'attente, 7 jours)
                                              omc-alarms-huawei   (apparition / disparition -> alarmes actives)
                                                     │ gsm_huawei_alarms.prom
                                               node-exporter ──▶ Prometheus (job gsm-omc-textfile) ──▶ application
```

- Les traps sont **conservés bruts** dès la réception, même avant que la correspondance soit écrite :
  rien n'est perdu pendant la mise au point, et tout est rejoué une fois la configuration complétée.
- Aucun OID Huawei n'est supposé : la correspondance (quel champ porte le numéro d'alarme, le nom, la
  gravité, le NE…) est écrite à partir des **traps réellement reçus** (`inspecter`) et de la **MIB de
  l'interface nord** fournie par Huawei pour votre version.
- Secrets SNMP uniquement dans `.env.omc` ; le conteneur de traitement n'a aucun accès réseau.

## Mise en place

```bash
cd ~/gsm-supervision
./scripts/snmp_alarms.sh huawei init        # configuration + informations pour l'administrateur OSS
nano .env.omc                               # OMC_HUAWEI_SNMP_V3_* (ou OMC_HUAWEI_SNMP_COMMUNITY)
./scripts/snmp_alarms.sh huawei recevoir    # démarre la réception sur UDP 162
./scripts/snmp_alarms.sh huawei test-local  # trap de test envoyé depuis ce serveur : la chaîne fonctionne ?
# -> l'administrateur OSS déclare la destination sur le MAE ; attendre quelques alarmes
./scripts/snmp_alarms.sh huawei inspecter   # types de traps reçus, OID et valeurs d'exemple
nano config/exporters/huawei_snmp.json      # remplacer les A_COMPLETER
./scripts/snmp_alarms.sh huawei tester      # rejoue les traps reçus : alarmes actives reconstituées
./scripts/snmp_alarms.sh huawei activer     # publication pour Prometheus
./scripts/snmp_alarms.sh huawei etat
```

### À demander à l'administrateur OSS

| Élément | Détail |
|---|---|
| Destination des traps | IP du serveur de supervision, port UDP 162 (ou `SNMP_TRAP_PORT`) |
| Version et sécurité | SNMPv3 de préférence (utilisateur, authentification, chiffrement) ; à défaut v2c (communauté) |
| Type d'envoi | **Inform** de préférence (acquitté et réémis par le MAE en cas de perte) ; sinon Trap |
| Identifiant moteur (engine ID) du MAE | obligatoire en SNMPv3 **pour des Trap** (`OMC_HUAWEI_SNMP_V3_ENGINE_ID`) ; inutile pour des Inform |
| MIB de l'interface nord | pour identifier les OID (numéro d'alarme, nom, gravité, objet, date, apparition / disparition) |
| Synchronisation des alarmes | si l'interface nord permet de renvoyer les alarmes actives (après une coupure), la procédure |
| Filtres | périmètre envoyé (toutes les alarmes radio, ou seulement certaines gravités) |

Pare-feu du serveur : autoriser **UDP 162 entrant depuis l'IP du MAE uniquement**, et indiquer cette IP
dans `.env` (`HUAWEI_SNMP_SOURCES=<IP_MAE>`) : les traps venant d'ailleurs sont ignorés.

### Remplir la correspondance (`config/exporters/huawei_snmp.json`)

`inspecter` liste, pour chaque type de trap reçu, les OID et des exemples de valeurs décodées. Renseigner :

| Clé | Contenu |
|---|---|
| `event.by` | `trap_oid` si l'apparition et la disparition sont des types de traps différents ; `varbind` si un champ l'indique (`event.oid` + valeurs) |
| `event.raise` / `clear` / `ignore` | types de traps (ou valeurs) d'apparition, de disparition, et à ignorer (battement de cœur…) |
| `fields.alarm_id` | **numéro unique de l'alarme**, identique dans l'apparition et la disparition |
| `fields.name`, `code`, `severity`, `ne_name`, `location`, `occurred` | OID des autres informations (`null` si absent) |
| `severity_map` | chaque valeur de gravité → `CRITICAL`, `MAJOR`, `MINOR`, `WARNING` |
| `site_id.regex` / `from` | extraction du code site Mobilis (par défaut : 5 chiffres dans le nom du NE puis la localisation) |
| `timezone` | fuseau des dates texte envoyées par l'OMC (défaut Africa/Algiers) ; les DateAndTime SNMP sont reconnus |
| `expire_after_days` | facultatif : retirer une alarme sans disparition reçue au-delà de N jours |

Les chaînes sont décodées en UTF-8 (puis GBK, Latin-1) : accents conservés.

### Déclarer la source dans l'application

**Administration › Sources OMC** : connecteur « Prometheus / Alertmanager », équipementier Huawei.

- Si la source `PROM-HUAWEI` existe déjà (états par fichiers, docs/12) : lui ajouter la partie `alarms`.
- Sinon, créer `PROM-HUAWEI-ALARMES` (alarmes seules) :

```json
{
  "url": "http://prometheus:9090",
  "health_query": "(time() - gsm_alarm_receiver_heartbeat_timestamp_seconds{vendor=\"${vendor}\"}) < bool 120",
  "min_series": 0,
  "status": { "query": "gsm_ne_oper_status{vendor=\"${vendor}\", job=\"gsm-omc-textfile\"}" },
  "alarms": {
    "source": "promql",
    "query": "gsm_ne_active_alarm{vendor=\"${vendor}\", job=\"gsm-omc-textfile\"}",
    "labels": { "alarm_id": "alarm_id", "element_id": "ne_id", "site_id": "site_id",
                "code": "code", "severity": "severity", "description": "description" }
  }
}
```

Vérifier avant d'activer : `docker compose exec collector python -m app.cli test-source PROM-HUAWEI-ALARMES`.

Les alarmes apparaissent dans l'écran **Alarmes** et la fiche de chaque site (rattachement par code site,
zéros de tête et correspondances de codes compris). Pour qu'une alarme fasse passer un site **DOWN** ou
**DÉGRADÉ** (ex. `NodeB Unavailable`, `OML Fault`), créer puis **valider** la règle dans **Administration ›
Règles d'états** ; une alarme seule ne fournit pas l'état UP des sites sans alarme (il vient de l'export
d'état des NE, docs/12).

## Fiabilité

| Situation | Effet |
|---|---|
| Récepteur ou traitement arrêté | battement de cœur vieilli → source en **ÉCHEC** ; alerte Prometheus `GsmRecepteurAlarmesArrete` ; les alarmes déjà connues restent affichées |
| Redémarrage | état des alarmes actives conservé (volume `snmp-huawei`) ; les traps reçus entre-temps sont traités au redémarrage |
| Trap perdu (UDP) | une alarme peut rester affichée ou manquer : utiliser la synchronisation de l'interface nord si elle existe, ou `expire_after_days` |
| Type de trap inconnu | compté dans `gsm_alarm_receiver_unknown_trap{trap_oid}` : à classer dans `event` |

## Vérifié

- Tests automatisés `backend/tests/test_snmp_alarms.py` (OID fictifs) : décodage des chaînes longues et
  accentuées, filtre des sources, apparition / disparition / traps ignorés ou inconnus, dates, reprise
  après redémarrage, ligne en cours d'écriture, configuration incomplète.
- Chaîne réelle en local : Net-SNMP 5.9 (`snmptrapd`, traps v2c et v3 authPriv, communauté erronée
  rejetée) → exporteur → node_exporter 1.9.1 → Prometheus 3.11.0 → application : alarmes créées sur les
  bons sites, puis terminées à la réception du trap de disparition.
- Non vérifié : traps réels du MAE (à faire avec `inspecter` puis `tester`).
