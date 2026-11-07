#!/usr/bin/env bash
# =============================================================================
# Mise en place d'un exporteur d'OMC par fichiers (node_exporter, collecteur textfile)
#
#   ./scripts/omc_exporter.sh huawei aide
#   ./scripts/omc_exporter.sh huawei init                 1. prépare la configuration et le dossier d'exports
#   ./scripts/omc_exporter.sh huawei inspecter <export>   2. analyse un export RÉEL (colonnes, valeurs)
#   ./scripts/omc_exporter.sh huawei tester               3. lit le dernier export, affiche les métriques (n'écrit rien)
#   ./scripts/omc_exporter.sh huawei demarrer             4. lance node-exporter + l'exporteur, recharge Prometheus
#   ./scripts/omc_exporter.sh huawei etat                 5. vérifie ce que Prometheus reçoit
#   ./scripts/omc_exporter.sh huawei arreter
#
# Lecture seule : rien n'est installé ni modifié sur le serveur OMC. L'OMC (ou une tâche
# planifiée) dépose ses exports dans ${OMC_EXPORT_DIR:-./omc-exports}/<vendor>/ sur CE serveur.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

VENDOR="${1:-}"
CMD="${2:-aide}"
case "$VENDOR" in
  huawei) ;;
  ericsson|zte) echo "Exporteur $VENDOR : service à déclarer dans docker-compose.prometheus.yml (même modèle que huawei)."; exit 1 ;;
  *) sed -n '2,15p' "$0"; exit 1 ;;
esac

DC="docker compose -f docker-compose.yml -f docker-compose.prometheus.yml"
SCRIPT=tools/omc_textfile_exporter/omc_textfile_exporter.py
CFG=config/exporters/${VENDOR}.json
EXPORT_DIR="$(grep -E '^OMC_EXPORT_DIR=' .env 2>/dev/null | tail -1 | cut -d= -f2- || true)"
EXPORT_DIR="${EXPORT_DIR:-./omc-exports}/${VENDOR}"
SERVICE=omc-exporter-${VENDOR}

ok()   { printf '\033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✘\033[0m %s\n' "$*"; exit 1; }

py() {   # python3 du serveur s'il existe, sinon conteneur jetable (rien à installer)
  if command -v python3 >/dev/null 2>&1; then python3 "$@"
  else docker run --rm -i -v "$PWD":/w:ro -w /w python:3.13-slim python "$@"; fi
}

prom_query() {
  curl -s -G "http://127.0.0.1:${PROMETHEUS_PORT:-9090}/api/v1/query" --data-urlencode "query=$1" \
    | py -c 'import json,sys
d=json.load(sys.stdin)
r=d.get("data",{}).get("result",[])
print("  (aucune série)" if not r else "\n".join("  "+json.dumps(x["metric"],ensure_ascii=False)+" = "+x["value"][1] for x in r[:15]))'
}

case "$CMD" in
  aide|help)
    sed -n '2,15p' "$0" ;;

  init)
    mkdir -p config/exporters "$EXPORT_DIR"
    if [[ -f "$CFG" ]]; then ok "$CFG existe déjà (non modifié)"
    else cp tools/omc_textfile_exporter/${VENDOR}.example.json "$CFG"; ok "Configuration créée : $CFG"; fi
    ok "Dossier des exports de l'OMC : $EXPORT_DIR"
    echo
    echo "Ensuite :"
    echo "  1. Faire déposer les exports de l'OMC dans $EXPORT_DIR (SFTP/FTP de l'OMC, ou tâche planifiée)"
    echo "  2. ./scripts/omc_exporter.sh $VENDOR inspecter $EXPORT_DIR/<un_export>.csv"
    echo "  3. Remplacer les A_COMPLETER de $CFG, puis : ./scripts/omc_exporter.sh $VENDOR tester" ;;

  inspecter)
    FILE="${3:?Usage : $0 $VENDOR inspecter <fichier_export>}"
    [[ -f "$FILE" ]] || die "Fichier introuvable : $FILE"
    if command -v python3 >/dev/null 2>&1; then python3 "$SCRIPT" --inspect "$FILE" ${4:+--delimiter "$4"}
    else
      D="$(cd "$(dirname "$FILE")" && pwd)"
      docker run --rm -v "$PWD/$SCRIPT":/app/x.py:ro -v "$D":/in:ro python:3.13-slim \
        python /app/x.py --inspect "/in/$(basename "$FILE")" ${4:+--delimiter "$4"}
    fi ;;

  tester)
    [[ -f "$CFG" ]] || die "$CFG absent : lancer d'abord « $0 $VENDOR init »"
    mkdir -p "$EXPORT_DIR"
    echo "Lecture du dernier export de $EXPORT_DIR (aucune écriture) :"
    $DC run --rm --no-deps "$SERVICE" python /app/omc_textfile_exporter.py --config /config/${VENDOR}.json --dry-run \
      | tee /tmp/omc_${VENDOR}_test.prom | grep -vE '^# ' | head -25
    N=$(grep -c '^gsm_ne_oper_status' /tmp/omc_${VENDOR}_test.prom || true)
    if [[ "$N" -gt 0 ]]; then ok "$N équipement(s) prêts à être publiés (fichier complet : /tmp/omc_${VENDOR}_test.prom)"
    else die "Aucun équipement publié : voir le message gsm_exporter_error ci-dessus"; fi
    grep -q '^gsm_exporter_unmapped_status' /tmp/omc_${VENDOR}_test.prom \
      && warn "Des valeurs d'état ne sont pas dans status_map (gsm_exporter_unmapped_status) : à compléter" || true ;;

  demarrer)
    [[ -f "$CFG" ]] || die "$CFG absent : lancer d'abord « $0 $VENDOR init »"
    "$0" "$VENDOR" tester >/dev/null || die "Le test échoue : lancer « $0 $VENDOR tester » pour le détail"
    # Profil actif pour toutes les commandes docker compose suivantes (up, down, ps…)
    if ! grep -qE "^COMPOSE_PROFILES=.*\b${VENDOR}\b" .env 2>/dev/null; then
      [[ -s .env && "$(tail -c1 .env)" != "" ]] && echo >> .env
      if grep -qE '^COMPOSE_PROFILES=' .env 2>/dev/null; then sed -i "s/^COMPOSE_PROFILES=\(.*\)/COMPOSE_PROFILES=\1,${VENDOR}/" .env
      else echo "COMPOSE_PROFILES=${VENDOR}" >> .env; fi
      ok "COMPOSE_PROFILES mis à jour dans .env"
    fi
    $DC --profile "$VENDOR" up -d node-exporter "$SERVICE"
    $DC restart prometheus >/dev/null && ok "Prometheus rechargé (job gsm-omc-textfile)"
    echo "Attendre une minute puis : $0 $VENDOR etat" ;;

  etat)
    $DC --profile "$VENDOR" ps node-exporter "$SERVICE" prometheus
    echo; echo "Dernières lignes de l'exporteur :"; $DC --profile "$VENDOR" logs --tail=5 "$SERVICE" || true
    echo; echo "Cible Prometheus (1 = node-exporter joignable) :"; prom_query 'up{job="gsm-omc-textfile"}'
    echo "Lecture de l'export (1 = OK) :";              prom_query "gsm_exporter_up{vendor=\"${VENDOR}\"}"
    echo "Équipements publiés :";                        prom_query "count(gsm_ne_oper_status{vendor=\"${VENDOR}\", job=\"gsm-omc-textfile\"})"
    echo "Par état (1 UP, 0 DOWN, 2 DÉGRADÉ) :";         prom_query "count by (technology) (gsm_ne_oper_status{vendor=\"${VENDOR}\", job=\"gsm-omc-textfile\"} == 0)"
    echo "Valeurs d'état non reconnues :";               prom_query "gsm_exporter_unmapped_status{vendor=\"${VENDOR}\"}"
    echo "Erreur éventuelle :";                          prom_query "gsm_exporter_error{vendor=\"${VENDOR}\"}" ;;

  arreter)
    $DC --profile "$VENDOR" stop "$SERVICE"
    ok "Exporteur $VENDOR arrêté (node-exporter laissé en service). L'application passera la source en ÉCHEC, jamais en DOWN." ;;

  *) die "Commande inconnue : $CMD (aide, init, inspecter, tester, demarrer, etat, arreter)" ;;
esac
