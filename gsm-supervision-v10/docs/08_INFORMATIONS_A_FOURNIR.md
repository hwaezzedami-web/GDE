# 8. Informations à fournir pour connecter les OMC réels

Pour **chaque serveur OMC** (Ericsson, Huawei, ZTE) à raccorder, merci de rassembler les éléments ci-dessous. Ils permettent de compléter le profil du connecteur sans rien supposer du format.

## A. Identification de la plateforme

1. Équipementier, nom et **version exacte** du logiciel OMC (et des correctifs).
2. Périmètre géré : technologies (2G / 3G / 4G / 5G), régions ou wilayas, nombre approximatif de sites et d'équipements.
3. Existe-t-il plusieurs instances (par technologie, par région) ? Lister chacune.

## B. Interfaces réellement disponibles (une seule suffit)

Pour chaque interface envisagée, indiquer si elle est **licenciée, activée et autorisée** pour un usage de supervision en lecture :

| Interface | Informations nécessaires |
|---|---|
| Export de fichiers planifié (inventaire, états, alarmes actives) | Contenu de chaque export, format (CSV, XML…), séparateur, encodage, fréquence, nom des fichiers, emplacement (répertoire partagé ou serveur SFTP), durée de conservation |
| Serveur SFTP | Adresse, port, répertoire, compte **lecture seule**, authentification (clé de préférence), **empreinte de la clé d'hôte** |
| Accès SQL lecture seule | SGBD et version, adresse, port, nom de base, compte dédié lecture seule, vues/tables autorisées, **requêtes validées par l'équipementier ou l'exploitant** |
| Interface nord (NBI) / API | Documentation officielle de l'interface pour la version installée, protocole, authentification, environnement de test |

## C. Échantillons (indispensables)

Fichiers ou extraits **réels**, éventuellement anonymisés, couvrant :
1. L'inventaire (sites et équipements, au moins 50 lignes avec les 4 technologies si présentes).
2. Les états opérationnels / de connexion, avec **au moins un équipement hors service** et un équipement en service.
3. Les alarmes actives (si disponibles), avec plusieurs gravités.
4. La liste exhaustive des **valeurs possibles** de la colonne d'état et de la colonne de gravité, avec leur signification.

## D. Règles métier

1. Champ portant le **code site opérateur** commun aux technologies (colonne dédiée, ou règle d'extraction depuis le nom de l'équipement, avec exemples).
2. Source des **coordonnées GPS** (OMC, base de planification radio, autre référentiel) et format (degrés décimaux, DMS…).
3. Source de la **wilaya / commune** de chaque site, et référentiel utilisé par les OMC : 48, 58 ou 69 wilayas. À défaut, la wilaya est déduite des coordonnées grâce aux contours embarqués ; pour une précision officielle, fournir les contours de l'INCT/ONS en GeoJSON (voir 09_CARTOGRAPHIE.md).
4. Valeurs qui signifient **DOWN**, **UP**, et le cas échéant **DÉGRADÉ**.
5. Alarmes qui signifient réellement « site hors service » (codes, textes), à valider par l'équipe RAN.
6. Fréquence de collecte souhaitée (1, 5 ou 15 min) compatible avec la charge acceptable par l'OMC ; délai de confirmation d'une panne souhaité.
7. Fuseau horaire des horodatages fournis par l'OMC.

## D bis. Si la collecte passe par Prometheus

1. URL de Prometheus (et d'Alertmanager), version, authentification (basique, jeton, TLS et autorité de certification).
2. Pour chaque OMC : exporteur utilisé (SNMP, JSON, SQL, fichiers…), nom du job et labels des cibles.
3. Noms des métriques et labels publiés pour l'état des équipements, le référentiel et les alarmes (ou confirmation qu'ils suivent le contrat de [10_PROMETHEUS.md](10_PROMETHEUS.md)), avec la signification de chaque valeur d'état.
4. Résultat d'une requête PromQL d'exemple par OMC (quelques séries, anonymisées si nécessaire).

## E. Réseau et sécurité

1. Adresse du serveur de supervision et flux à ouvrir vers chaque OMC (protocole, port).
2. Politique de gestion des secrets (fichier protégé, coffre-fort, secrets Docker).
3. Exigences internes : TLS (certificat de l'application), annuaire d'entreprise (LDAP/AD) éventuel pour l'authentification, durée de conservation des journaux.
4. Fond de carte : les postes ont-ils accès à Internet (OpenStreetMap) ? Sinon, la carte embarquée suffit ; un serveur de tuiles interne reste possible pour un fond détaillé (routes, villes).

## F. Interlocuteurs

Référent OMC par équipementier, référent réseau / sécurité, validateur côté RAN pour la recette.

---

Une fois ces éléments reçus : renseigner le profil (`backend/app/collector/profiles/<équipementier>.yaml` ou la configuration de la source), créer la source **désactivée**, exécuter `test-source`, puis dérouler la procédure de validation ([07_VALIDATION.md](07_VALIDATION.md)) avant activation.
