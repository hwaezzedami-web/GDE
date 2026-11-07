"""Connecteur Prometheus : états des équipements et alarmes depuis Prometheus / Alertmanager.

Chaîne de collecte :
    OMC  --(exporteur, lecture seule)-->  Prometheus  --(API HTTP, PromQL)-->  ce connecteur
                                          Alertmanager --(API v2, lecture)-->  ce connecteur

Le connecteur n'utilise que des requêtes en lecture :
    GET /api/v1/query          (Prometheus, requête instantanée PromQL)
    GET /api/v2/alerts         (Alertmanager, alertes actives)

Chaque série Prometheus devient une « ligne » (labels + valeur + horodatage) et
réutilise le même mapping que les fichiers d'export (collector/mapping.py).

Règles de fiabilité :
  - Prometheus injoignable, requête en erreur, exporteur down (up == 0) ou aucune
    série renvoyée  -> collecte en ÉCHEC : les états ne sont pas modifiés et
    vieillissent jusqu'à INCONNU. Jamais de bascule DOWN par défaut de collecte.
  - Une série absente (équipement non publié) ne désactive pas l'équipement :
    inventory_complete = False ; son état vieillit normalement.
  - Prometheus ne renvoie que les échantillons de moins de 5 min (lookback par
    défaut) : régler stale_after_s >= fréquence de collecte + 5 min + marge.

Configuration : profiles/prometheus.yaml (contrat de métriques), surchargée par
la configuration de la source. Documentation : docs/10_PROMETHEUS.md.
"""
from __future__ import annotations

import hashlib
import json
import math
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import yaml

from ..mapping import TabularMapper, ensure_configured
from ..model import CollectResult, NSite
from ..secrets import get_secret
from .base import BaseConnector, ConnectorError, ConnectorNotConfigured
from .vendor import deep_merge

PROFILE = Path(__file__).resolve().parents[1] / "profiles" / "prometheus.yaml"
VALUE = "__value__"
TIMESTAMP = "__timestamp__"
FINGERPRINT = "__fingerprint__"
ALARM_ID = "__alarm_id__"
TRANSIENT_ERRORS = {"timeout", "canceled", "unavailable", "internal"}


def _substitute(obj, vendor: str):
    if isinstance(obj, str):
        return obj.replace("${vendor}", vendor)
    if isinstance(obj, list):
        return [_substitute(x, vendor) for x in obj]
    if isinstance(obj, dict):
        return {k: _substitute(v, vendor) for k, v in obj.items()}
    return obj


def _canonical_value(v: str | None) -> str | None:
    """'1' / '1.0' / '1e0' -> '1' ; 'NaN' / '+Inf' -> None."""
    if v is None:
        return None
    try:
        f = float(v)
    except ValueError:
        return str(v)
    if math.isnan(f) or math.isinf(f):
        return None
    return str(int(f)) if f.is_integer() else repr(f)


def _label_fingerprint(labels: dict) -> str:
    return hashlib.sha1(json.dumps(labels, sort_keys=True).encode("utf-8")).hexdigest()[:16]


class PrometheusConnector(BaseConnector):
    """Utilisable pour les trois équipementiers (vendor de la source)."""

    def __init__(self, spec, transport: httpx.BaseTransport | None = None):
        super().__init__(spec)
        profile_file = spec.config.get("profile_file") or PROFILE
        try:
            profile = yaml.safe_load(Path(profile_file).read_text(encoding="utf-8")) or {}
        except FileNotFoundError:
            raise ConnectorNotConfigured(f"Profil introuvable : {profile_file}")
        cfg = deep_merge(profile, spec.config)
        self.cfg = _substitute(cfg, spec.vendor.lower())
        ensure_configured(self.cfg)
        self._transport = transport          # injecté par les tests
        self._clients: list[httpx.Client] = []

    # ------------------------------------------------------------------ HTTP
    def _client(self, base_url: str) -> httpx.Client:
        u = urlparse(base_url or "")
        if u.scheme not in ("http", "https") or not u.netloc:
            raise ConnectorNotConfigured(f"URL invalide : {base_url!r} (attendu http(s)://hôte:port)")
        cfg = self.cfg
        if cfg.get("ca_file"):
            try:
                verify: bool | ssl.SSLContext = ssl.create_default_context(cafile=cfg["ca_file"])
            except (OSError, ssl.SSLError) as exc:
                raise ConnectorNotConfigured(f"ca_file illisible : {cfg['ca_file']} ({exc})") from exc
        else:
            verify = bool(cfg.get("tls_verify", True))
        auth = None
        headers = {"Accept": "application/json", "User-Agent": "gsm-supervision-collector/1.1"}
        user = get_secret(self.spec.code, "USERNAME", required=False)
        if user:
            auth = (user, get_secret(self.spec.code, "PASSWORD", required=False) or "")
        token = get_secret(self.spec.code, "BEARER_TOKEN", required=False)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        kw = dict(base_url=base_url.rstrip("/"), timeout=float(cfg.get("timeout_s", 30)), verify=verify,
                  auth=auth, headers=headers, trust_env=bool(cfg.get("use_env_proxy", False)),
                  follow_redirects=False)
        if self._transport is not None:
            kw["transport"] = self._transport
        c = httpx.Client(**kw)
        self._clients.append(c)
        return c

    def _get_json(self, client: httpx.Client, path: str, params) -> object:
        try:
            r = client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise ConnectorError(f"Délai dépassé vers {client.base_url}{path}", transient=True) from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(f"{client.base_url} injoignable : {exc.__class__.__name__}: {exc}",
                                 transient=True) from exc
        if r.status_code in (401, 403):
            raise ConnectorError(f"Accès refusé par {client.base_url} (HTTP {r.status_code}) : vérifier "
                                 f"OMC_{self.spec.code}_USERNAME/_PASSWORD/_BEARER_TOKEN", transient=False)
        try:
            body = r.json()
        except ValueError:
            raise ConnectorError(f"Réponse non JSON de {client.base_url}{path} (HTTP {r.status_code})",
                                 transient=r.status_code >= 500)
        if r.status_code >= 400 and not (isinstance(body, dict) and body.get("status") == "error"):
            raise ConnectorError(f"HTTP {r.status_code} sur {client.base_url}{path}", transient=r.status_code >= 500)
        return body

    def query(self, client: httpx.Client, promql: str, res: CollectResult, what: str) -> list[dict]:
        """Requête instantanée PromQL -> lignes {labels…, __value__, __timestamp__}."""
        timeout = int(self.cfg.get("timeout_s", 30))
        body = self._get_json(client, "/api/v1/query", {"query": promql, "timeout": f"{timeout}s"})
        if not isinstance(body, dict):
            raise ConnectorError(f"Réponse Prometheus inattendue ({what})", transient=False)
        if body.get("status") != "success":
            etype = body.get("errorType", "")
            raise ConnectorError(f"Prometheus ({what}) : {etype} — {body.get('error', '')} [requête : {promql}]",
                                 transient=etype in TRANSIENT_ERRORS)
        for w in body.get("warnings") or []:
            res.warnings.append(f"Prometheus ({what}) : {w}")
        data = body.get("data") or {}
        if data.get("resultType") != "vector":
            raise ConnectorError(f"La requête {what} doit renvoyer un vecteur instantané "
                                 f"(reçu : {data.get('resultType')}) [requête : {promql}]", transient=False)
        rows = []
        for item in data.get("result") or []:
            ts, val = item.get("value") or (None, None)
            row = dict(item.get("metric") or {})
            row[VALUE] = _canonical_value(val)
            row[TIMESTAMP] = f"{float(ts):.3f}" if ts is not None else None
            rows.append(row)
        return rows

    def alertmanager_alerts(self, res: CollectResult) -> list[dict]:
        a = self.cfg.get("alarms") or {}
        client = self._client(a.get("url"))
        params = [("active", "true"), ("silenced", str(bool(a.get("include_silenced"))).lower()),
                  ("inhibited", "false")] + [("filter", f) for f in (a.get("filter") or [])]
        body = self._get_json(client, "/api/v2/alerts", params)
        if not isinstance(body, list):
            raise ConnectorError("Réponse Alertmanager inattendue (liste d'alertes attendue)", transient=False)
        rows = []
        for al in body:
            if (al.get("status") or {}).get("state") not in (None, "active"):
                continue
            row = dict(al.get("labels") or {})
            for k, v in (al.get("annotations") or {}).items():
                row[f"annotations.{k}"] = v
            row[FINGERPRINT] = al.get("fingerprint")
            row["__startsAt__"] = al.get("startsAt")
            rows.append(row)
        return rows

    # ------------------------------------------------------------------ collecte
    def _mapper(self) -> TabularMapper:
        cfg = self.cfg
        lab = cfg.get("labels") or {}
        common = {k: lab.get(k) for k in ("site_id", "element_id", "element_name", "element_type", "technology")}
        inventory = dict(common, site_name=lab.get("site_name"), latitude=lab.get("latitude"),
                         longitude=lab.get("longitude"), wilaya_code=lab.get("wilaya_code"),
                         wilaya=lab.get("wilaya"), commune=lab.get("commune"), address=lab.get("address"))
        st = cfg.get("status") or {}
        if st.get("from", "value") == "label":
            if not st.get("label"):
                raise ConnectorNotConfigured("status.label requis quand status.from = label")
            status_col = st["label"]
        else:
            status_col = VALUE
        status = dict(common, status=status_col, observed_at=TIMESTAMP,
                      last_communication=lab.get("last_communication"))
        al = (cfg.get("alarms") or {})
        alab = al.get("labels") or {}
        is_am = al.get("source") == "alertmanager"
        alarms = {
            "alarm_id": ALARM_ID, "element_id": alab.get("element_id"),
            "site_id": alab.get("site_id"), "code": alab.get("code"), "severity": alab.get("severity"),
            "description": alab.get("description"),
            "raised_at": "__startsAt__" if is_am else (VALUE if al.get("raised_at_from_value", True) else None),
        }
        return TabularMapper({
            "columns": {"inventory": inventory, "status": status, "alarms": alarms},
            "value_maps": cfg.get("value_maps") or {},
            "derive": cfg.get("derive") or {},
            "timestamps": {"format": None, "timezone": "UTC"},
            "extra_columns": cfg.get("extra_labels") or [],
        })

    def collect(self) -> CollectResult:
        cfg = self.cfg
        res = CollectResult(inventory_complete=False, alarms_complete=False, details={"connector": "prometheus"})
        client = self._client(cfg.get("url"))
        now = datetime.now(timezone.utc)
        mapper = self._mapper()

        # 1. Santé de la chaîne de collecte (exporteurs)
        hq = cfg.get("health_query")
        if hq:
            health = self.query(client, hq, res, "santé")
            if not health:
                raise ConnectorError(
                    "La requête de santé ne renvoie aucune cible : exporteur non déclaré dans Prometheus, ou "
                    f"health_query à adapter (« {hq} », ou null pour la désactiver)", transient=True)
            down = [r for r in health if r[VALUE] != "1"]
            res.details["targets"] = {"total": len(health), "down": len(down)}
            if len(down) == len(health):
                names = ", ".join(sorted({r.get("instance", "?") for r in down}))[:300]
                raise ConnectorError(f"Exporteur(s) de l'OMC injoignable(s) par Prometheus (up == 0) : {names}. "
                                     "Ce n'est pas une panne radio : les états vieilliront jusqu'à INCONNU.",
                                     transient=True)
            for r in down:
                res.warnings.append(f"Cible Prometheus en échec (up == 0) : {r.get('instance', '?')} "
                                    f"— ses équipements ne sont pas mis à jour")

        # 2. Référentiel (noms, coordonnées) — optionnel
        iq = (cfg.get("info") or {}).get("query")
        if iq:
            info_rows = self.query(client, iq, res, "référentiel")
            res.details["info_series"] = len(info_rows)
            mapper.map_inventory(info_rows, res, now)

        # 3. États
        sq = (cfg.get("status") or {}).get("query")
        if not sq:
            raise ConnectorNotConfigured("status.query requis")
        status_rows = self.query(client, sq, res, "états")
        res.details["status_series"] = len(status_rows)
        if len(status_rows) < int(cfg.get("min_series", 1)):
            raise ConnectorError(
                f"La requête d'état ne renvoie que {len(status_rows)} série(s) (minimum {cfg.get('min_series', 1)}) : "
                f"exporteur arrêté ou requête incorrecte [requête : {sq}]", transient=True)
        for r in status_rows:
            if r[VALUE] is None and (cfg.get("status") or {}).get("from", "value") == "value":
                r[VALUE] = "NaN"
        mapper.map_status(status_rows, res, now)

        # Tout équipement doit être rattaché à un site (créé au besoin, sans écraser le référentiel)
        known = {s.external_id for s in res.sites}
        for e in res.elements:
            if e.site_external_id not in known:
                res.sites.append(NSite(external_id=e.site_external_id))
                known.add(e.site_external_id)
        # Équipements du référentiel sans série d'état : présents, état non fourni par cette collecte
        res.details["elements_without_status"] = sum(1 for e in res.elements if e.oper_status is None)

        # 4. Alarmes actives
        a = cfg.get("alarms") or {}
        src = a.get("source")
        if src == "alertmanager":
            rows = self.alertmanager_alerts(res)
        elif src == "promql":
            if not a.get("query"):
                raise ConnectorNotConfigured("alarms.query requis quand alarms.source = promql")
            rows = self.query(client, a["query"], res, "alarmes")
            for r in rows:
                r[FINGERPRINT] = _label_fingerprint({k: v for k, v in r.items() if not k.startswith("__")})
        elif src in (None, "", "none"):
            rows = None
        else:
            raise ConnectorNotConfigured(f"alarms.source inconnu : {src} (alertmanager, promql ou null)")
        if rows is not None:
            # Identifiant : label alarm_id s'il existe, sinon empreinte stable de l'alerte
            id_label = (a.get("labels") or {}).get("alarm_id")
            for r in rows:
                r[ALARM_ID] = (r.get(id_label) if id_label else None) or r.get(FINGERPRINT)
            mapper.map_alarms(rows, res)
            res.alarms_complete = True       # ensemble complet des alarmes actives
            res.details["alarms"] = len(rows)
        return res

    def close(self) -> None:
        for c in self._clients:
            c.close()
        self._clients.clear()

