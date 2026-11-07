"""Accès en lecture seule à des fichiers d'export : répertoire local (ou monté) et SFTP.

Le SFTP impose la vérification de la clé d'hôte (fichier known_hosts) : un
serveur inconnu est refusé, pour éviter toute interception.
"""
from __future__ import annotations

import fnmatch
import logging
import os
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..connectors.base import ConnectorError, ConnectorNotConfigured
from ..secrets import MissingSecret, get_secret

log = logging.getLogger(__name__)


@dataclass
class RemoteFile:
    name: str
    mtime: datetime
    size: int


class FileFetcher(ABC):
    @abstractmethod
    def list(self, pattern: str) -> list[RemoteFile]:
        """Fichiers correspondant au motif, du plus récent au plus ancien."""

    @abstractmethod
    def read(self, name: str, max_bytes: int) -> bytes:
        ...

    def latest(self, pattern: str) -> RemoteFile | None:
        files = self.list(pattern)
        return files[0] if files else None

    def close(self) -> None:
        pass


class LocalDirFetcher(FileFetcher):
    def __init__(self, path: str):
        self.root = Path(path)
        if not self.root.is_dir():
            raise ConnectorError(f"Répertoire d'export inaccessible : {path}", transient=True)

    def list(self, pattern: str) -> list[RemoteFile]:
        out = []
        for p in self.root.iterdir():
            if p.is_file() and fnmatch.fnmatch(p.name, pattern):
                st = p.stat()
                out.append(RemoteFile(p.name, datetime.fromtimestamp(st.st_mtime, timezone.utc), st.st_size))
        return sorted(out, key=lambda f: (f.mtime, f.name), reverse=True)

    def read(self, name: str, max_bytes: int) -> bytes:
        p = (self.root / name).resolve()
        if self.root.resolve() not in p.parents:
            raise ConnectorError("Chemin de fichier refusé", transient=False)
        if p.stat().st_size > max_bytes:
            raise ConnectorError(f"Fichier {name} trop volumineux (> {max_bytes} octets)", transient=False)
        return p.read_bytes()


class SftpFetcher(FileFetcher):
    def __init__(self, source_code: str, cfg: dict):
        try:
            import paramiko
        except ImportError as exc:  # pragma: no cover
            raise ConnectorNotConfigured("Module paramiko non installé") from exc
        host = cfg.get("host")
        if not host:
            raise ConnectorNotConfigured("sftp.host non renseigné")
        known_hosts = cfg.get("known_hosts_file")
        if not known_hosts or not os.path.isfile(known_hosts):
            raise ConnectorNotConfigured(
                "sftp.known_hosts_file obligatoire (empreinte de la clé du serveur, ex. ssh-keyscan -H <hôte>)")
        try:
            username = get_secret(source_code, "USERNAME")
            password = get_secret(source_code, "PASSWORD", required=False)
            key_path = get_secret(source_code, "PRIVATE_KEY_PATH", required=False)
            passphrase = get_secret(source_code, "PRIVATE_KEY_PASSPHRASE", required=False)
        except MissingSecret as exc:
            raise ConnectorNotConfigured(str(exc)) from exc
        if not password and not key_path:
            raise ConnectorNotConfigured("Fournir un mot de passe ou une clé privée SFTP (variables OMC_<CODE>_…)")
        self.remote_dir = cfg.get("remote_dir", ".")
        timeout = float(cfg.get("timeout_s", 30))
        self._ssh = paramiko.SSHClient()
        self._ssh.load_host_keys(known_hosts)
        self._ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            self._ssh.connect(host, port=int(cfg.get("port", 22)), username=username, password=password,
                              key_filename=key_path, passphrase=passphrase, timeout=timeout,
                              banner_timeout=timeout, auth_timeout=timeout,
                              allow_agent=False, look_for_keys=False)
            self._sftp = self._ssh.open_sftp()
            self._sftp.get_channel().settimeout(timeout)
        except paramiko.AuthenticationException as exc:
            raise ConnectorError(f"Authentification SFTP refusée par {host}", transient=False) from exc
        except paramiko.SSHException as exc:
            raise ConnectorError(f"Erreur SSH vers {host} : {exc}", transient=True) from exc
        except (socket.error, OSError) as exc:
            raise ConnectorError(f"Connexion SFTP impossible vers {host} : {exc}", transient=True) from exc

    def list(self, pattern: str) -> list[RemoteFile]:
        out = []
        for a in self._sftp.listdir_attr(self.remote_dir):
            if fnmatch.fnmatch(a.filename, pattern):
                out.append(RemoteFile(a.filename, datetime.fromtimestamp(a.st_mtime or 0, timezone.utc),
                                      a.st_size or 0))
        return sorted(out, key=lambda f: (f.mtime, f.name), reverse=True)

    def read(self, name: str, max_bytes: int) -> bytes:
        if "/" in name or name.startswith(".."):
            raise ConnectorError("Nom de fichier refusé", transient=False)
        path = f"{self.remote_dir.rstrip('/')}/{name}"
        if self._sftp.stat(path).st_size > max_bytes:
            raise ConnectorError(f"Fichier {name} trop volumineux", transient=False)
        with self._sftp.open(path, "rb") as fh:
            return fh.read()

    def close(self) -> None:
        try:
            self._sftp.close()
        finally:
            self._ssh.close()


def make_fetcher(source_code: str, config: dict) -> FileFetcher:
    transport = config.get("transport", "local")
    if transport == "local":
        path = (config.get("local") or {}).get("path")
        if not path:
            raise ConnectorNotConfigured("local.path non renseigné")
        return LocalDirFetcher(path)
    if transport == "sftp":
        return SftpFetcher(source_code, config.get("sftp") or {})
    raise ConnectorNotConfigured(f"Transport inconnu : {transport} (local ou sftp)")
