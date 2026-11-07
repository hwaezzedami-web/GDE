#!/usr/bin/env bash
# =============================================================================
# Alarmes d'OMC par traps SNMP (interface nord) -> Prometheus -> application
#
#   ./scripts/snmp_alarms.sh huawei aide
#   ./scripts/snmp_alarms.sh huawei init          1. configuration + informations à donner à l'administrateur OSS
#   ./scripts/snmp_alarms.sh huawei recevoir      2. démarre la réception (traps conservés bruts)
#   ./scripts/snmp_alarms.sh huawei test-local    3. envoie un trap de TEST depuis ce serveur (vérifie la chaîne)
#   ./scripts/snmp_alarms.sh huawei inspecter     4. résumé des traps reçus de l'OMC (aide à la configuration)
#   ./scripts/snmp_alarms.sh huawei tester        5. rejoue les traps reçus avec la configuration (n'écrit rien)
#   ./scripts/snmp_alarms.sh huawei activer       6. publie les alarmes actives pour Prometheus
#   ./scripts/snmp_alarms.sh huawei etat          7. vérifie ce que Prometheus reçoit
#   ./scripts/snmp_alarms.sh huawei arreter
#
# Lecture seule vis-à-vis de l'OMC : il envoie ses alarmes, rien n'est modifié de son côté
# en dehors de la déclaration de cette destination de traps par l'administrateur OSS.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

VENDOR="${1:-}"
CMD="${2:-aide}"
[[ "$VENDOR" == "huawei" ]] || { sed -n '2,18p' "$0"; exit 1; }
DC="docker compose -f docker-compose.yml -f docker-compose.prometheus.yml"
PROFILE=huawei-snmp
CFG=config/exporters/huawei_snmp.json
RX=snmp-trap-huawei
EXP=omc-alarms-huawei
PORT="$(grep -E '^SNMP_TRAP_PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2- || true)"; PORT="${PORT:-162}"

ok()   { printf '\033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✘\033[0m %s\n' "$*"; exit 1; }
envv() { grep -E "^$1=" .env.omc 2>/dev/null | tail -1 | cut -d= -f2- || true; }

add_profile() {   # profil actif pour toutes les commandes docker compose (up, down, ps…)
  grep -qE "^COMPOSE_PROFILES=.*\b${PROFILE}\b" .env 2>/dev/null && return 0
  [[ -s .env && "$(tail -c1 .env)" != "" ]] && echo >> .env
  if grep -qE '^COMPOSE_PROFILES=' .env 2>/dev/null; then sed -i "s/^COMPOSE_PROFILES=\(.*\)/COMPOSE_PROFILES=\1,${PROFILE}/" .env
  else echo "COMPOSE_PROFILES=${PROFILE}" >> .env; fi
  ok "COMPOSE_PROFILES mis à jour dans .env"
}

prom_query() {
  curl -s -G "http://127.0.0.1:${PROMETHEUS_PORT:-9090}/api/v1/query" --data-urlencode "query=$1" \
    | docker run --rm -i python:3.13-slim python -c 'import json,sys
d=json.load(sys.stdin); r=d.get("data",{}).get("result",[])
print("  (aucune série)" if not r else "\n".join("  "+json.dumps(x["metric"],ensure_ascii=False)+" = "+x["value"][1] for x in r[:15]))'
}

case "$CMD" in
  aide|help) sed -n '2,18p' "$0" ;;

  init)
    mkdir -p config/exporters
    if [[ -f "$CFG" ]]; then ok "$CFG existe déjà (non modifié)"
    else cp tools/snmp_trap_receiver/huawei_snmp.example.json "$CFG"; ok "Configuration créée : $CFG"; fi
    [[ -f .env.omc ]] || { cp .env.omc.example .env.omc; chmod 600 .env.omc; ok ".env.omc créé (droits 600)"; }
    if [[ -n "$(envv OMC_HUAWEI_SNMP_V3_USER)$(envv OMC_HUAWEI_SNMP_COMMUNITY)" ]]; then ok "Identifiants SNMP présents dans .env.omc"
    else warn "Ajouter dans .env.omc les identifiants SNMP (modèle en fin de .env.omc.example) : OMC_HUAWEI_SNMP_V3_USER, …"; fi
    IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
    echo
    echo "À transmettre à l'administrateur OSS (destination des traps de l'interface nord SNMP du MAE) :"
    echo "  adresse : ${IP:-<IP de ce serveur>}   port : UDP ${PORT}"
    echo "  SNMPv3 (recommandé) : utilisateur, protocoles et mots de passe identiques à ceux de .env.omc"
    echo "  Envoi en INFORM de préférence (acquitté) ; en TRAP v3, fournir l'engine ID du MAE -> OMC_HUAWEI_SNMP_V3_ENGINE_ID"
    echo "  Demander aussi la MIB de l'interface nord (alarmes) pour cette version du MAE."
    echo
    echo "Pare-feu de ce serveur : autoriser UDP ${PORT} depuis l'IP du MAE (ex. ufw allow from <IP_MAE> to any port ${PORT} proto udp)."
    echo "Restreindre aussi l'accès dans .env : HUAWEI_SNMP_SOURCES=<IP_MAE>"
    echo
    echo "Ensuite : $0 huawei recevoir" ;;

  recevoir)
    [[ -n "$(envv OMC_HUAWEI_SNMP_V3_USER)$(envv OMC_HUAWEI_SNMP_COMMUNITY)" ]] \
      || die "Identifiants SNMP absents de .env.omc (lancer « $0 huawei init »)"
    [[ -f "$CFG" ]] || die "$CFG absent : lancer « $0 huawei init »"
    add_profile
    $DC --profile "$PROFILE" up -d --build "$RX"
    sleep 3
    $DC --profile "$PROFILE" logs --tail=5 "$RX"
    ok "Réception démarrée sur UDP ${PORT}. Traps conservés bruts, même avant de compléter la configuration."
    echo "Vérifier la chaîne : $0 huawei test-local   — puis, quand le MAE envoie : $0 huawei inspecter" ;;

  test-local)
    C="$(envv OMC_HUAWEI_SNMP_COMMUNITY)"; U="$(envv OMC_HUAWEI_SNMP_V3_USER)"
    T=1.3.6.1.4.1.99999   # OID FICTIF réservé au test : apparaîtra comme « type de trap non reconnu »
    PAYLOAD="'' $T.0.1 $T.1.1 s 'TEST-$(date +%s)' $T.1.2 s 'Trap de test du serveur de supervision'"
    if [[ -n "$U" ]]; then
      AP="$(envv OMC_HUAWEI_SNMP_V3_AUTH_PROTOCOL)"; PP="$(envv OMC_HUAWEI_SNMP_V3_PRIV_PROTOCOL)"
      SEC="-l authNoPriv -a '${AP:-SHA}' -A '$(envv OMC_HUAWEI_SNMP_V3_AUTH_PASSWORD)'"
      if [[ -n "$(envv OMC_HUAWEI_SNMP_V3_PRIV_PASSWORD)" ]]; then
        SEC="-l authPriv -a '${AP:-SHA}' -A '$(envv OMC_HUAWEI_SNMP_V3_AUTH_PASSWORD)' -x '${PP:-AES}' -X '$(envv OMC_HUAWEI_SNMP_V3_PRIV_PASSWORD)'"
      fi
      $DC exec -T "$RX" sh -c "snmptrap -v 3 -e '$(envv OMC_HUAWEI_SNMP_V3_ENGINE_ID)' -u '$U' $SEC 127.0.0.1:1162 $PAYLOAD"
    elif [[ -n "$C" ]]; then
      $DC exec -T "$RX" sh -c "snmptrap -v 2c -c '$C' 127.0.0.1:1162 $PAYLOAD"
    else die "Identifiants SNMP absents de .env.omc"; fi
    sleep 2
    N=$($DC exec -T "$RX" sh -c 'cat /data/spool/traps-*.jsonl 2>/dev/null | grep -c "hex:544553542D" || true')
    [[ "${N:-0}" -gt 0 ]] && ok "Trap de test reçu et enregistré ($N au total) : la chaîne de réception fonctionne." \
      || die "Trap de test non enregistré : voir « $DC logs $RX »" ;;

  inspecter)
    $DC --profile "$PROFILE" run --rm --no-deps "$EXP" exporter --inspect ;;

  tester)
    [[ -f "$CFG" ]] || die "$CFG absent : lancer « $0 huawei init »"
    $DC --profile "$PROFILE" run --rm --no-deps -e EXIT_ON_CONFIG_ERROR=1 "$EXP" exporter \
      --config /config/huawei_snmp.json --dry-run | tee /tmp/huawei_alarms_test.prom | grep -vE '^# ' | head -30
    N=$(grep -c '^gsm_ne_active_alarm' /tmp/huawei_alarms_test.prom || true)
    ok "$N alarme(s) active(s) reconstituée(s) à partir des traps reçus (fichier : /tmp/huawei_alarms_test.prom)"
    grep -q 'gsm_alarm_receiver_unknown_trap' /tmp/huawei_alarms_test.prom \
      && warn "Des types de traps ne sont pas reconnus (gsm_alarm_receiver_unknown_trap) : à classer dans event.raise / clear / ignore" || true
    grep -q 'site_id=' /tmp/huawei_alarms_test.prom || warn "Aucun code site extrait : vérifier site_id.regex et site_id.from" ;;

  activer)
    "$0" huawei tester >/dev/null || die "Le test échoue : lancer « $0 huawei tester » pour le détail"
    add_profile
    $DC --profile "$PROFILE" up -d node-exporter "$EXP"
    $DC kill -s SIGHUP prometheus >/dev/null && ok "Prometheus rechargé"
    echo "Dans l'application : source des alarmes à déclarer (docs/13_ALARMES_SNMP.md). Puis : $0 huawei etat" ;;

  etat)
    $DC --profile "$PROFILE" ps "$RX" "$EXP" node-exporter
    echo; echo "Réception :"; $DC --profile "$PROFILE" logs --tail=3 "$RX" || true
    echo; echo "Traitement :"; $DC --profile "$PROFILE" logs --tail=3 "$EXP" || true
    echo; echo "Alarmes actives :";        prom_query 'gsm_alarm_receiver_active{vendor="huawei"}'
    echo "Dernier trap reçu (âge en s) :"; prom_query 'time() - gsm_alarm_receiver_last_trap_timestamp_seconds{vendor="huawei"}'
    echo "Traps par type :";            prom_query 'gsm_alarm_receiver_traps{vendor="huawei"}'
    echo "Alarmes par gravité :";       prom_query 'count by (severity) (gsm_ne_active_alarm{vendor="huawei"})'
    echo "Types de traps non reconnus :"; prom_query 'gsm_alarm_receiver_unknown_trap{vendor="huawei"}' ;;

  arreter)
    $DC --profile "$PROFILE" stop "$EXP" "$RX"
    ok "Réception et traitement arrêtés (traps reçus et état conservés dans le volume snmp-huawei)." ;;

  *) die "Commande inconnue : $CMD" ;;
esac
