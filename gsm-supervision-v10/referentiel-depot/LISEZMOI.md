# Dossier de dépôt du référentiel de sites

Monté en lecture seule dans le service de collecte (`/data/referentiel`).
Déposer ici l'export du référentiel des sites de l'opérateur : **KMZ, KML, XLSX, CSV ou GeoJSON**.

- L'import automatique est **désactivé par défaut** : l'activer dans *Référentiel → Paramètres → Dossier surveillé*.
- Le fichier le plus récent est importé **une seule fois** (empreinte SHA-256), après 30 s sans modification.
- La correspondance des colonnes est celle du dernier import réussi du même format (faire un premier
  import depuis l'interface pour la valider).
- Le garde-fou de synchronisation s'applique : un fichier qui retirerait trop de sites est refusé
  (visible dans *Historique des imports*).

Ces fichiers contiennent des données réelles de l'opérateur : ils ne doivent pas être versionnés
(voir `.gitignore`) ni copiés hors du serveur.
