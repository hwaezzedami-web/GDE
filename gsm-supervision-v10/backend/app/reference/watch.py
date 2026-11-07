"""Import automatique du référentiel depuis un dossier surveillé (service de collecte).

Le dernier fichier déposé (KMZ, KML, XLSX, CSV, GeoJSON) est importé une seule fois (empreinte
SHA-256), avec la correspondance de colonnes du dernier import réussi du même format, sinon la
détection automatique. Le garde-fou de synchronisation s'applique : un import qui retirerait trop
de sites est refusé et apparaît dans l'historique, à reprendre depuis l'interface.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

from sqlalchemy import text

from ..config import get_settings
from ..db import session_scope
from ..services.settings_service import get_setting
from .parsers import ReferenceFileError
from .service import apply_plan, build_plan

log = logging.getLogger("gsm.reference")
EXTENSIONS = {".kmz", ".kml", ".xlsx", ".xlsm", ".csv", ".geojson", ".json"}
STABLE_S = 30          # fichier non modifié depuis 30 s (copie terminée)
IMPORT_LOCK = 7421004


def pick_file(folder: Path, now: float | None = None) -> Path | None:
    now = now or time.time()
    if not folder.is_dir():
        return None
    files = [f for f in folder.iterdir()
             if f.is_file() and f.suffix.lower() in EXTENSIONS and not f.name.startswith((".", "~$"))
             and now - f.stat().st_mtime >= STABLE_S]
    return max(files, key=lambda f: f.stat().st_mtime, default=None)


def run_watch(folder: str | None = None, force: bool = False) -> dict | None:
    folder_p = Path(folder or get_settings().reference_watch_dir)
    with session_scope() as db:
        cfg = get_setting(db, "reference")
        if not (cfg["watch_enabled"] or force):
            return None
        f = pick_file(folder_p)
        if f is None:
            return None
        content = f.read_bytes()
        sha = hashlib.sha256(content).hexdigest()
        if db.execute(text("SELECT 1 FROM reference_imports WHERE file_sha256 = :h AND status <> 'FAILED' LIMIT 1"),
                      {"h": sha}).first():
            return None
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": IMPORT_LOCK})
        ext = f.suffix.lower().lstrip(".")
        fmt = {"xlsm": "xlsx", "json": "geojson"}.get(ext, ext)
        prev = db.execute(text("""SELECT mapping, counts FROM reference_imports
                                  WHERE status = 'APPLIED' AND file_format = :f ORDER BY started_at DESC LIMIT 1"""),
                          {"f": fmt}).first()
        mapping = prev[0] if prev else None
        digits = (prev[1] or {}).get("code_digits") if prev else None
        mode = cfg["watch_mode"]
        try:
            try:
                plan = build_plan(db, f.name, content, mapping, mode, digits)
            except ValueError:
                if mapping is None:
                    raise
                plan = build_plan(db, f.name, content, None, mode, digits)   # colonnes changées
            res = apply_plan(db, plan, mode, None, "WATCH", f.name)
        except (ReferenceFileError, ValueError) as exc:
            db.rollback()
            db.execute(text("""
                INSERT INTO reference_imports (origin, file_name, file_sha256, file_format, mode, status,
                                               finished_at, messages)
                VALUES ('WATCH', :n, :h, :f, :m, 'FAILED', now(), CAST(:msg AS jsonb))"""),
                {"n": f.name[:200], "h": sha, "f": fmt[:20], "m": mode, "msg": json.dumps([str(exc)])})
            log.error("Import automatique du référentiel %s en échec : %s", f.name, exc)
            return {"status": "FAILED", "message": str(exc)}
        log.info("Import automatique du référentiel %s : %s", f.name, res["status"])
        return res
