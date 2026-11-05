"""Configuration de la journalisation (console + fichier optionnel)."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def setup_logging(level: str = "INFO", log_dir: Path | None = None, name: str = "api") -> None:
    root = logging.getLogger()
    if getattr(root, "_gsm_configured", False):
        return
    root.setLevel(level.upper())
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(console)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_dir / f"{name}.log", maxBytes=20 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(handler)
    root._gsm_configured = True  # type: ignore[attr-defined]
