"""Filtres combinables communs à la carte, au tableau, au tableau de bord et aux exports.

Un seul constructeur de clause WHERE garantit que les compteurs du tableau de
bord sont toujours cohérents avec ce qui est affiché sur la carte.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from fastapi import HTTPException, Query

from .models import REF_STATUSES, STATUSES, TECHNOLOGIES, VENDORS

# État affiché : un site du référentiel qu'aucun OMC ne remonte est « non supervisé » (gris clair),
# ce qui le distingue d'un site supervisé dont l'état est inconnu (collecte interrompue, données périmées).
DISPLAY_STATUSES = STATUSES + ("UNSUPERVISED",)
REF_FILTER_VALUES = REF_STATUSES + ("NONE", "ALL")


def display_status_sql(a: str = "s") -> str:
    return f"(CASE WHEN {a}.in_reference AND NOT {a}.is_supervised THEN 'UNSUPERVISED' ELSE {a}.status END)"


def default_scope_sql(a: str = "s") -> str:
    """Périmètre par défaut : sites en service ou temporairement arrêtés au référentiel, et tout site
    effectivement remonté par un OMC. Les sites en projet ou démontés non supervisés sont masqués."""
    return (f"(NOT {a}.in_reference OR {a}.ref_status IN ('IN_SERVICE', 'TEMP_OFF', 'OTHER') "
            f"OR {a}.is_supervised)")


@dataclass
class SiteFilters:
    wilaya: list[int] = field(default_factory=list)
    region: list[str] = field(default_factory=list)
    commune: str | None = None
    q: str | None = None
    vendor: list[str] = field(default_factory=list)
    tech: list[str] = field(default_factory=list)
    status: list[str] = field(default_factory=list)
    omc: list[str] = field(default_factory=list)
    outage_from: datetime | None = None
    outage_to: datetime | None = None
    bbox: tuple[float, float, float, float] | None = None
    stale: bool | None = None
    dr: list[str] = field(default_factory=list)
    ref: list[str] = field(default_factory=list)       # catégories du référentiel, NONE (hors référentiel), ALL
    supervised: bool | None = None

    def where(self, alias: str = "s") -> tuple[str, dict]:
        a = alias
        clauses = [f"{a}.is_active"]
        p: dict = {}
        if self.wilaya:
            clauses.append(f"{a}.wilaya_code = ANY(:f_wilaya)")
            p["f_wilaya"] = self.wilaya
        if self.region:
            clauses.append(f"{a}.wilaya_code IN (SELECT code FROM wilayas WHERE region = ANY(:f_region))")
            p["f_region"] = self.region
        if self.commune:
            clauses.append(f"{a}.commune ILIKE :f_commune")
            p["f_commune"] = f"%{_escape_like(self.commune)}%"
        if self.q:
            clauses.append(f"({a}.name ILIKE :f_q OR {a}.external_id ILIKE :f_q)")
            p["f_q"] = f"%{_escape_like(self.q)}%"
        if self.vendor:
            clauses.append(f"{a}.vendor = ANY(:f_vendor)")
            p["f_vendor"] = self.vendor
        if self.tech:
            clauses.append(f"{a}.technologies && CAST(:f_tech AS text[])")
            p["f_tech"] = self.tech
        if self.status:
            clauses.append(f"{display_status_sql(a)} = ANY(:f_status)")
            p["f_status"] = self.status
        if "ALL" in self.ref:
            pass
        elif self.ref:
            cats = [r for r in self.ref if r in REF_STATUSES]
            parts = []
            if cats:
                parts.append(f"({a}.in_reference AND {a}.ref_status = ANY(:f_ref))")
                p["f_ref"] = cats
            if "NONE" in self.ref:
                parts.append(f"NOT {a}.in_reference")
            clauses.append("(" + " OR ".join(parts) + ")")
        else:
            clauses.append(default_scope_sql(a))
        if self.dr:
            clauses.append(f"{a}.dr = ANY(:f_dr)")
            p["f_dr"] = self.dr
        if self.supervised is not None:
            clauses.append(f"{a}.is_supervised = :f_sup")
            p["f_sup"] = self.supervised
        if self.omc:
            clauses.append(f"""EXISTS (SELECT 1 FROM site_elements fe JOIN omc_sources fo ON fo.id = fe.omc_source_id
                                 WHERE fe.site_id = {a}.id AND fe.is_active AND fo.code = ANY(:f_omc))""")
            p["f_omc"] = self.omc
        if self.outage_from or self.outage_to:
            cond = ["fh.site_id = " + a + ".id", "fh.entity_type = 'SITE'", "fh.new_status = 'DOWN'"]
            if self.outage_from:
                cond.append("fh.changed_at >= :f_out_from")
                p["f_out_from"] = self.outage_from
            if self.outage_to:
                cond.append("fh.changed_at <= :f_out_to")
                p["f_out_to"] = self.outage_to
            clauses.append("EXISTS (SELECT 1 FROM status_history fh WHERE " + " AND ".join(cond) + ")")
        if self.bbox:
            clauses.append(f"{a}.geom && ST_MakeEnvelope(:f_x1, :f_y1, :f_x2, :f_y2, 4326)::geography")
            p.update(f_x1=self.bbox[0], f_y1=self.bbox[1], f_x2=self.bbox[2], f_y2=self.bbox[3])
        if self.stale is not None:
            clauses.append(f"{a}.is_stale = :f_stale")
            p["f_stale"] = self.stale
        return " AND ".join(clauses), p

    def describe(self) -> dict:
        return {k: (v.isoformat() if isinstance(v, datetime) else v)
                for k, v in self.__dict__.items() if v not in (None, [], ())}


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")[:100]


def _upper_list(values: list[str] | None, allowed: tuple[str, ...], name: str) -> list[str]:
    out = []
    for v in values or []:
        for part in v.split(","):
            part = part.strip().upper()
            if not part:
                continue
            if part not in allowed:
                raise HTTPException(422, f"Valeur invalide pour {name} : {part}")
            out.append(part)
    return out


def site_filters(
    wilaya: list[str] | None = Query(None, description="Codes wilaya (répétable ou séparés par des virgules)"),
    region: list[str] | None = Query(None),
    commune: str | None = Query(None, max_length=100),
    q: str | None = Query(None, max_length=100, description="Nom ou identifiant du site"),
    vendor: list[str] | None = Query(None),
    tech: list[str] | None = Query(None),
    status: list[str] | None = Query(None),
    omc: list[str] | None = Query(None),
    outage_from: datetime | None = Query(None, description="Panne détectée après (ISO 8601)"),
    outage_to: datetime | None = Query(None),
    bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
    stale: bool | None = Query(None),
    dr: list[str] | None = Query(None, description="Directions régionales (référentiel)"),
    ref: list[str] | None = Query(None, description="Catégorie au référentiel : IN_SERVICE, TEMP_OFF, PLANNED, "
                                                    "REMOVED, OTHER, NONE (hors référentiel), ALL"),
    supervised: bool | None = Query(None, description="Site remonté par au moins un OMC"),
) -> SiteFilters:
    wil: list[int] = []
    for v in wilaya or []:
        for part in v.split(","):
            if part.strip():
                if not part.strip().isdigit():
                    raise HTTPException(422, f"Code wilaya invalide : {part}")
                wil.append(int(part))
    bb = None
    if bbox:
        try:
            x1, y1, x2, y2 = (float(x) for x in bbox.split(","))
        except ValueError:
            raise HTTPException(422, "bbox invalide (attendu : minLon,minLat,maxLon,maxLat)")
        bb = (x1, y1, x2, y2)
    omc_codes = [c.strip().upper() for v in (omc or []) for c in v.split(",") if c.strip()]
    regions = [r.strip() for v in (region or []) for r in v.split(",") if r.strip()]
    return SiteFilters(
        wilaya=wil, region=regions, commune=commune or None, q=(q or "").strip() or None,
        vendor=_upper_list(vendor, VENDORS + ("MULTI", "UNKNOWN"), "vendor"),
        tech=_upper_list(tech, TECHNOLOGIES, "tech"),
        status=_upper_list(status, DISPLAY_STATUSES, "status"),
        omc=omc_codes, outage_from=outage_from, outage_to=outage_to, bbox=bb, stale=stale,
        dr=[d.strip() for v in (dr or []) for d in v.split(",") if d.strip()][:50],
        ref=_upper_list(ref, REF_FILTER_VALUES, "ref"), supervised=supervised,
    )
