"""Persistente Anwendungseinstellungen (JSON in ``%APPDATA%/MVR Enhancer``).

``Settings.load()`` liest die Konfigurationsdatei; fehlt sie oder ist sie
korrupt, werden Defaults verwendet — es wird nie eine Exception nach
aussen geworfen. ``save()`` schreibt atomar (Temp-Datei + ``os.replace``),
damit ein Absturz waehrend des Schreibens keine kaputte Config hinterlaesst.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import tempfile
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_CONFIG_FILENAME = "config.json"
_MAX_RECENT_FILES = 5


@dataclasses.dataclass
class Settings:
    recent_files: list = dataclasses.field(default_factory=list)
    gdtf_library_dir: str = ""
    last_export_dir: str = ""
    group_by_position: bool = True
    share_user: str = ""
    share_password_enc: str = ""
    base_dir: str = dataclasses.field(default="", repr=False, compare=False)

    @classmethod
    def load(cls, base_dir: str | None = None) -> Settings:
        """Laedt die Settings aus ``<base_dir>/config.json``.

        Fehlt die Datei oder ist sie nicht als JSON-Objekt lesbar, werden
        Defaults zurueckgegeben. Unbekannte Schluessel werden ignoriert,
        fehlende Schluessel werden defaultet.
        """
        resolved_base_dir = base_dir if base_dir is not None else _default_base_dir()
        config_path = os.path.join(resolved_base_dir, _CONFIG_FILENAME)

        data = {}
        try:
            with open(config_path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
            else:
                log.warning("config.json enthaelt kein Objekt — verwende Defaults")
        except FileNotFoundError:
            pass
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            log.warning("config.json konnte nicht gelesen werden (%s) — verwende Defaults",
                        type(e).__name__)

        field_names = {f.name for f in dataclasses.fields(cls)} - {"base_dir"}
        kwargs = {k: v for k, v in data.items() if k in field_names}

        recent_files = kwargs.get("recent_files")
        if not isinstance(recent_files, list):
            kwargs["recent_files"] = []
        else:
            kwargs["recent_files"] = [
                entry for entry in recent_files
                if isinstance(entry, dict) and "path" in entry and "ts" in entry
            ][:_MAX_RECENT_FILES]

        settings = cls(**kwargs)
        settings.base_dir = resolved_base_dir
        return settings

    def save(self) -> None:
        """Schreibt die Settings atomar nach ``<base_dir>/config.json``."""
        base_dir = self.base_dir or _default_base_dir()
        os.makedirs(base_dir, exist_ok=True)
        config_path = os.path.join(base_dir, _CONFIG_FILENAME)

        payload = {
            "recent_files": self.recent_files,
            "gdtf_library_dir": self.gdtf_library_dir,
            "last_export_dir": self.last_export_dir,
            "group_by_position": self.group_by_position,
            "share_user": self.share_user,
            "share_password_enc": self.share_password_enc,
        }

        fd, tmp_path = tempfile.mkstemp(dir=base_dir, prefix=".config-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, config_path)
        except BaseException:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise

    def add_recent(self, path: str) -> None:
        """Fuegt ``path`` vorne in die Liste zuletzt geoeffneter Dateien ein.

        Dedupliziert case-insensitiv (Windows-Pfade), verschiebt bereits
        vorhandene Eintraege nach vorne und begrenzt die Liste auf 5 Eintraege.
        """
        lowered = path.lower()
        self.recent_files = [
            entry for entry in self.recent_files if entry["path"].lower() != lowered
        ]
        self.recent_files.insert(0, {
            "path": path,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        self.recent_files = self.recent_files[:_MAX_RECENT_FILES]


def _default_base_dir() -> str:
    return os.path.join(os.environ["APPDATA"], "MVR Enhancer")
