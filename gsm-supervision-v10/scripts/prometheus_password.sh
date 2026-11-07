#!/usr/bin/env bash
# Crée ou met à jour un compte d'accès web à Prometheus et Alertmanager
# (/prometheus/ et /alertmanager/ derrière le nginx de l'application).
#   ./scripts/prometheus_password.sh <utilisateur>          (mot de passe demandé)
#   ./scripts/prometheus_password.sh --supprimer <utilisateur>
# Le fichier ne contient que des empreintes (APR1), jamais les mots de passe.
set -euo pipefail
cd "$(dirname "$0")/.."
FILE=config/nginx-auth/htpasswd
mkdir -p config/nginx-auth && chmod 755 config/nginx-auth
touch "$FILE"
if [[ "${1:-}" == "--supprimer" ]]; then
  USER_="${2:?Usage : $0 --supprimer <utilisateur>}"
  sed -i "/^${USER_}:/d" "$FILE"; echo "Compte « $USER_ » supprimé."; exit 0
fi
USER_="${1:?Usage : $0 <utilisateur>}"
[[ "$USER_" =~ ^[A-Za-z0-9._-]{3,32}$ ]] || { echo "Nom d'utilisateur invalide (3 à 32 caractères : lettres, chiffres, . _ -)"; exit 1; }
read -r -s -p "Mot de passe pour $USER_ : " P1; echo
read -r -s -p "Confirmation : " P2; echo
[[ "$P1" == "$P2" ]] || { echo "Les mots de passe diffèrent."; exit 1; }
[[ ${#P1} -ge 12 ]] || { echo "12 caractères minimum."; exit 1; }
HASH=$(printf '%s' "$P1" | openssl passwd -apr1 -stdin)
sed -i "/^${USER_}:/d" "$FILE"
echo "${USER_}:${HASH}" >> "$FILE"
chmod 644 "$FILE"          # lisible par nginx dans le conteneur (empreintes uniquement)
echo "Compte « $USER_ » enregistré dans $FILE (pris en compte immédiatement)."
