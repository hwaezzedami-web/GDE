#!/bin/sh
# Génère la configuration de snmptrapd à partir des variables d'environnement (secrets dans .env.omc)
# puis lance le récepteur. Aucun secret n'est écrit ailleurs que dans /run/snmp (mémoire du conteneur).
#   OMC_<CODE>_SNMP_COMMUNITY                       SNMP v2c (à éviter si v3 est possible)
#   OMC_<CODE>_SNMP_V3_USER / _V3_AUTH_PROTOCOL (SHA, SHA-256, SHA-512, MD5) / _V3_AUTH_PASSWORD
#   OMC_<CODE>_SNMP_V3_PRIV_PROTOCOL (AES, DES) / _V3_PRIV_PASSWORD / _V3_ENGINE_ID (identifiant moteur de l'OMC)
# SOURCE_CODE : préfixe des variables (ex. HUAWEI). SNMP_ALLOWED_SOURCES : adresses autorisées (lu par trap_handler).
set -eu
[ "${1:-}" = "exporter" ] && { shift; exec python3 /app/alarm_exporter.py "$@"; }
P="OMC_${SOURCE_CODE:?SOURCE_CODE manquant}_SNMP"
get() { eval "printf '%s' \"\${${P}_$1:-}\""; }
CONF=/run/snmp/snmptrapd.conf
umask 077
{
  echo "snmpTrapdAddr udp:1162"
  echo "disableAuthorization no"
  echo "doNotLogTraps yes"
  echo "traphandle default /usr/bin/python3 /app/trap_handler.py"
} > "$CONF"
N=0
if [ -n "$(get COMMUNITY)" ]; then
  echo "authCommunity execute $(get COMMUNITY)" >> "$CONF"; N=1
fi
if [ -n "$(get V3_USER)" ]; then
  AUTHP="$(get V3_AUTH_PROTOCOL)"; PRIVP="$(get V3_PRIV_PROTOCOL)"
  CRED="$(get V3_USER) ${AUTHP:-SHA} $(get V3_AUTH_PASSWORD)"
  if [ -n "$(get V3_PRIV_PASSWORD)" ]; then CRED="$CRED ${PRIVP:-AES} $(get V3_PRIV_PASSWORD)"; fi
  # Inform (acquitté, recommandé) : l'OMC découvre l'identifiant moteur de ce récepteur
  echo "createUser $CRED" >> "$CONF"
  # Trap (non acquitté) : l'identifiant moteur de l'OMC émetteur est obligatoire
  if [ -n "$(get V3_ENGINE_ID)" ]; then echo "createUser -e $(get V3_ENGINE_ID) $CRED" >> "$CONF"
  else echo "Information : ${P}_V3_ENGINE_ID vide -> seuls les INFORM SNMPv3 sont acceptés (traps v3 refusés)"; fi
  LEVEL=auth; if [ -n "$(get V3_PRIV_PASSWORD)" ]; then LEVEL=priv; fi
  echo "authUser execute $(get V3_USER) $LEVEL" >> "$CONF"; N=1
fi
[ "$N" = 1 ] || { echo "ERREUR : définir ${P}_COMMUNITY ou ${P}_V3_USER dans .env.omc"; exit 2; }
echo "Récepteur de traps SNMP (${SOURCE_CODE}) en écoute sur udp/1162 (port hôte : voir docker-compose)"
# -On : OID numériques ; -Ox : chaînes en hexadécimal (décodées ensuite sans perte d'accents) ; -m "" : sans MIB
exec snmptrapd -f -Lo -m "" -Onx -C -c "$CONF"
