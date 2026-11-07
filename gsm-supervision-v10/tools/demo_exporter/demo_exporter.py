#!/usr/bin/env python3
"""Exporteur Prometheus de DÉMONSTRATION — données 100 % FICTIVES.

Simule ce qu'un exporteur d'OMC doit publier selon le contrat de métriques du
projet (docs/10_PROMETHEUS.md), à partir de data/test/sites_fictifs.csv :

  gsm_ne_info{site_id, site_name, ne_id, ne_name, ne_type, technology, latitude, longitude,
              wilaya_code, commune, omc}                                   1
  gsm_ne_oper_status{site_id, ne_id, technology, omc}                     1 = en service, 0 = hors service
  gsm_ne_active_alarm{alarm_id, site_id, ne_id, code, severity, description, omc}
                                                                          début de l'alarme (horodatage Unix)

Le label « vendor » n'est PAS publié ici : il est ajouté par Prometheus (labels de
la cible dans prometheus.yml), une cible par équipementier / OMC. L'équipementier
voulu est passé en paramètre de collecte : /metrics?vendor=huawei

Aucune dépendance (bibliothèque standard). Usage :
  python3 demo_exporter.py --csv data/test/sites_fictifs.csv --port 9800
"""
from __future__ import annotations

import argparse
import csv
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ELEMENT_TYPE = {"2G": "BTS", "3G": "NODEB", "4G": "ENODEB", "5G": "GNODEB"}


def esc(v) -> str:
    return str(v).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def labels(d: dict) -> str:
    return "{" + ",".join(f'{k}="{esc(v)}"' for k, v in d.items() if v not in (None, "")) + "}"


class DemoNetwork:
    def __init__(self, csv_path: str, seed: int, p_fail: float, p_recover: float):
        self.rng = random.Random(seed)
        self.p_fail, self.p_recover = p_fail, p_recover
        self.lock = threading.Lock()
        self.elements: list[dict] = []
        with open(csv_path, encoding="utf-8") as fh:
            rows = csv.DictReader((line for line in fh if not line.lstrip().startswith("#")), delimiter=";")
            for r in rows:
                vendor = r["vendor"].lower()
                for t in r["technologies"].split("|"):
                    st = r["status"]
                    up = 0 if st == "DOWN" or (st == "DEGRADED" and t == r["technologies"].split("|")[-1]) else 1
                    self.elements.append({
                        "vendor": vendor, "site_id": r["site_code"], "site_name": r["site_name"],
                        "ne_id": f'{r["site_code"]}-{t}', "ne_name": f'{r["site_name"]}_{t}',
                        "ne_type": ELEMENT_TYPE[t], "technology": t, "latitude": r["latitude"],
                        "longitude": r["longitude"], "wilaya_code": r["wilaya_code"], "commune": r["commune"],
                        "omc": f"DEMO-OMC-{vendor.upper()}", "up": up,
                        "since": time.time() if not up else None,
                    })

    def tick(self) -> None:
        with self.lock:
            now = time.time()
            for e in self.elements:
                if e["up"] and self.rng.random() < self.p_fail:
                    e["up"], e["since"] = 0, now
                elif not e["up"] and self.rng.random() < self.p_recover:
                    e["up"], e["since"] = 1, None

    def render(self, vendor: str | None) -> str:
        with self.lock:
            els = [e for e in self.elements if vendor in (None, "", e["vendor"])]
            out = ["# HELP gsm_ne_info Référentiel des équipements radio (DONNÉES FICTIVES).",
                   "# TYPE gsm_ne_info gauge"]
            for e in els:
                out.append("gsm_ne_info" + labels({k: e[k] for k in (
                    "site_id", "site_name", "ne_id", "ne_name", "ne_type", "technology", "latitude", "longitude",
                    "wilaya_code", "commune", "omc")}) + " 1")
            out += ["# HELP gsm_ne_oper_status État opérationnel : 1 en service, 0 hors service (FICTIF).",
                    "# TYPE gsm_ne_oper_status gauge"]
            for e in els:
                out.append("gsm_ne_oper_status" + labels({k: e[k] for k in ("site_id", "ne_id", "technology", "omc")})
                           + f" {e['up']}")
            out += ["# HELP gsm_ne_active_alarm Alarme active ; valeur = début (horodatage Unix) (FICTIF).",
                    "# TYPE gsm_ne_active_alarm gauge"]
            for e in els:
                if not e["up"]:
                    out.append("gsm_ne_active_alarm" + labels({
                        "alarm_id": f"{e['ne_id']}-LINK", "site_id": e["site_id"], "ne_id": e["ne_id"],
                        "code": "DEMO-001", "severity": "critical",
                        "description": f"[FICTIF] Perte de liaison {e['technology']}", "omc": e["omc"],
                    }) + f" {int(e['since'])}")
            return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default="data/test/sites_fictifs.csv")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=9800)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--tick", type=float, default=30, help="secondes entre deux évolutions simulées")
    ap.add_argument("--p-fail", type=float, default=0.002)
    ap.add_argument("--p-recover", type=float, default=0.15)
    a = ap.parse_args()
    net = DemoNetwork(a.csv, a.seed, a.p_fail, a.p_recover)

    def loop():
        while True:
            time.sleep(a.tick)
            net.tick()
    threading.Thread(target=loop, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            u = urlparse(self.path)
            if u.path == "/metrics":
                vendor = (parse_qs(u.query).get("vendor") or [None])[0]
                body = net.render(vendor).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            elif u.path in ("/", "/health"):
                body = b"Exporteur de demonstration GSM (donnees FICTIVES) - voir /metrics?vendor=huawei\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
            else:
                body = b"not found\n"
                self.send_response(404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    print(f"Exporteur de démonstration (FICTIF) : {len(net.elements)} équipements sur http://{a.host}:{a.port}/metrics",
          flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
