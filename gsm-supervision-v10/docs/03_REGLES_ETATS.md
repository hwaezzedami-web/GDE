# 3. Règles d'états UP / DOWN / DÉGRADÉ / INCONNU

Implémentation : [`backend/app/services/status_engine.py`](../backend/app/services/status_engine.py) — tests : `tests/test_status_engine.py`, `tests/test_connectors_ingest.py`.

## Principe

1. **L'état d'un équipement vient de l'OMC** (`site_elements.oper_status`), après traduction de la valeur brute via la table `value_maps.status` de la source. La valeur brute est conservée (`raw_status`) pour traçabilité. Une valeur non reconnue donne `UNKNOWN` et un avertissement dans le journal de collecte — jamais `DOWN`.
2. **Fraîcheur** : si la dernière observation d'un équipement est plus ancienne que le seuil de sa source (`omc_sources.stale_after_s`, à défaut `default_stale_after_s` = 1 800 s), son état effectif devient `UNKNOWN`. Les sources « import CSV manuel » ne périment pas.
3. **Règles d'alarmes** (optionnelles) : une alarme active ne modifie l'état que si elle correspond à une règle **activée et validée** par un administrateur (même équipementier, code exact ou expression régulière sur la description). Effet `DOWN` ou `DEGRADED`, sur l'équipement concerné ou sur tout le site.
4. **Consolidation par site** :

| Situation | État du site |
|---|---|
| Aucun équipement à l'état connu (tous inconnus ou périmés) | **UNKNOWN** (gris) |
| Tous les équipements connus sont DOWN | **DOWN** (rouge) |
| Au moins un équipement DOWN ou DEGRADED, mais pas tous | **DEGRADED** (orange) — paramètre `partial_down_is_degraded` |
| Tous UP + alarme CRITICAL ou MAJOR active | **DEGRADED** — paramètre `major_alarm_degrades` |
| Tous UP + un équipement inconnu | **UP** (ou DEGRADED si `unknown_elements_policy = degrade`) |
| Tous UP | **UP** (vert) |

5. **Anti-rebond** : un passage à DOWN (resp. UP) n'est confirmé qu'après `down_confirm_s` (resp. `up_confirm_s`) secondes de persistance ; pendant l'attente, la fiche du site l'indique. La transition est horodatée à la **première détection**, pour que les durées de panne restent exactes. Valeurs par défaut : 0 (immédiat).
6. **Historisation** : chaque transition (site et équipement) est enregistrée dans `status_history` avec ancien / nouvel état, date, source et motif. Le retour UP après une panne est donc tracé avec son horodatage, et la durée est calculée par différence avec la transition suivante.

## Perte de connexion avec un OMC ≠ panne radio

- La collecte échoue → `collection_runs.status = FAILED`, `omc_sources.last_status = FAILED`, bandeau d'avertissement sur la carte, source en rouge dans le tableau de bord.
- Les états des sites **ne sont pas modifiés** : ils restent affichés avec la mention « données potentiellement obsolètes » sur la fiche.
- Après le seuil de péremption, les sites concernés passent **UNKNOWN (gris)** et le compteur « données périmées » augmente. Aucun site n'est mis DOWN du fait d'une coupure de collecte.
- Un fichier d'export trop ancien est refusé (`max_file_age_s`) : un OMC qui ne produit plus d'exports ne fait pas paraître des données périmées comme fraîches. Par défaut l'horodatage d'observation est la date du fichier, pas l'heure de lecture.

Ce scénario est couvert par le test `test_omc_outage_is_not_a_radio_outage`.

## Paramétrage

Écran **Administration › Règles d'états** (administrateur) ou API `PUT /api/admin/settings/status_rules`. Toute modification est validée (bornes), journalisée dans l'audit et appliquée immédiatement par une réévaluation complète.

| Paramètre | Défaut | Plage |
|---|---|---|
| `default_stale_after_s` | 1 800 | 60 s – 7 j |
| `down_confirm_s` | 0 | 0 – 24 h |
| `up_confirm_s` | 0 | 0 – 24 h |
| `unknown_elements_policy` | `ignore` | `ignore`, `degrade` |
| `partial_down_is_degraded` | vrai | booléen |
| `major_alarm_degrades` | vrai | booléen |

Par source (Administration › Sources OMC) : `stale_after_s` — à régler à **3 à 4 fois** la fréquence de collecte, pour tolérer une collecte manquée sans passer en inconnu.

## Règles à faire valider

Les indicateurs « fiables » de panne diffèrent selon l'OMC et sa version. À définir avec les experts de chaque équipementier, puis à saisir et valider :
- quelles valeurs d'état de connexion / opérationnel signifient DOWN (→ `value_maps.status` de la source) ;
- quelles alarmes signifient réellement « site hors service » (→ règles d'alarmes, portée Site ou Équipement) ;
- délais de confirmation acceptables pour l'exploitation.

## Disponibilité

`Disponibilité = 1 − (temps DOWN) / (temps observé − temps UNKNOWN)`, calculée à partir des transitions de site sur la période choisie (tableau de bord, regroupement par wilaya, équipementier, région ou site). Les périodes inconnues sont exclues pour ne pas pénaliser — ni avantager — un site dont les données manquent.
