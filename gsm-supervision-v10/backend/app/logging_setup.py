"""Journalisation technique : sortie standard + fichier tournant optionnel (LOG_DIR)."""
from __future__ import annotations

import logging
import logging.handlers
import os


def setup_logging(service: str, level: str = "INFO", log_dir: str | None = None) -> None:
    fmt = logging.Formatter(f"%(asctime)s %(levelname)-7s [{service}] %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level.upper())
    for h in list(root.handlers):
        root.removeHandler(h)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, f"{service}.log"), maxBytes=20 * 1024 * 1024, backupCount=10, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    logging.getLogger("uvicorn.access").setLevel("WARNING")
    logging.getLogger("apscheduler").setLevel("WARNING")
    logging.getLogger("paramiko").setLevel("WARNING")
