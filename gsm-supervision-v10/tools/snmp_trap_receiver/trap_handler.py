#!/usr/bin/env python3
"""Appelé par snmptrapd pour chaque trap reçu (traphandle) : enregistre le trap BRUT,
sans interprétation, dans le dossier d'attente (une ligne JSON par trap).

Entrée (format traphandle de Net-SNMP, options -On -Ox) :
  ligne 1 : nom d'hôte ; ligne 2 : adresse de transport ; puis « OID valeur » par ligne.
  Les chaînes d'octets arrivent en hexadécimal entre guillemets (« "4E 6F 64 65 " ») et sont
  conservées telles quelles (préfixe hex:) : le décodage (UTF-8, GBK…) est fait par l'exporteur.
Sortie : /data/spool/traps-AAAAMMJJ.jsonl  {"t": horodatage, "src": IP, "trap": OID, "vb": [[oid, valeur], …]}
Sources autorisées : SNMP_ALLOWED_SOURCES (IP ou réseaux CIDR séparés par des virgules ; vide = toutes).
"""
from __future__ import annotations

import fcntl
import ipaddress
import json
import os
import re
import sys
import time

SPOOL = os.environ.get("TRAP_SPOOL_DIR", "/data/spool")
TRAP_OID = ".1.3.6.1.6.3.1.1.4.1.0"           # snmpTrapOID.0 (SNMPv2-MIB)
HEX = re.compile(r'^"((?:[0-9A-Fa-f]{2} ?)*)"$')
SRC = re.compile(r"\[([0-9A-Fa-f.:]+)\]:\d+->")


def allowed(ip: str | None) -> bool:
    spec = [s.strip() for s in os.environ.get("SNMP_ALLOWED_SOURCES", "").split(",") if s.strip()]
    if not spec:
        return True
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in ipaddress.ip_network(s, strict=False) for s in spec)
    except ValueError:
        return False


def parse(lines: list[str]) -> dict:
    src = SRC.search(lines[1]) if len(lines) > 1 else None
    raw: list[list[str]] = []
    for ln in lines[2:]:
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith(".") or not raw:          # nouvel OID (numérique avec -On)
            oid, _, val = ln.partition(" ")
            raw.append([oid, val.strip()])
        else:                                      # suite d'une longue chaîne hexadécimale (16 octets par ligne)
            raw[-1][1] += " " + ln
    vb = []
    for oid, val in raw:
        val = re.sub(r"\s+", " ", val) if val.startswith('"') else val
        m = HEX.match(val)
        if m:
            val = "hex:" + m.group(1).replace(" ", "").upper()
        elif len(val) >= 2 and val[0] == val[-1] == '"':
            val = val[1:-1].replace('\\"', '"')
        vb.append([oid, val])
    trap = next((v for o, v in vb if o == TRAP_OID), None)
    return {"t": round(time.time(), 3), "src": src.group(1) if src else None, "trap": trap, "vb": vb}


def main() -> int:
    data = sys.stdin.read().splitlines()
    rec = parse(data)
    if not allowed(rec["src"]):
        print(f"Trap ignoré : source non autorisée {rec['src']}", file=sys.stderr)
        return 0
    os.makedirs(SPOOL, exist_ok=True)
    path = os.path.join(SPOOL, time.strftime("traps-%Y%m%d.jsonl", time.gmtime()))
    line = json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n"
    with open(path, "a", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)       # plusieurs traps simultanés : pas de lignes entremêlées
        fh.write(line)
        fh.flush()
        fcntl.flock(fh, fcntl.LOCK_UN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
