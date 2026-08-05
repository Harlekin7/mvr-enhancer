"""Zentrale Coerce-Helper fuer Fixture-/Plugbox-/Truss-Konstruktion.

Verhindert Schema-Drift zwischen den Fixture-Konstruktions-Pfaden in
link_server.py, parsing/export.py und parsing/mvr_reader.py.

Audit-Bezug: Q6, Q7, B7.
"""

from __future__ import annotations


def safe_str(value, default: str = "") -> str:
    """Konvertiert beliebigen Input zu sauberem String (gestrippt)."""
    if value is None:
        return default
    try:
        return str(value).strip()
    except Exception:  # noqa: BLE001 — Coerce-Helper darf breit fangen
        return default


def safe_int(value, default: int = 0) -> int:
    """Konvertiert Input zu int. Akzeptiert auch '42.7'-Strings."""
    if value is None:
        return default
    if isinstance(value, bool):  # bool ist subclass von int — separat
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (ValueError, TypeError):
        return default


def safe_float(value, default: float = 0.0) -> float:
    """Konvertiert Input zu float. Akzeptiert Komma-Dezimal."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", "."))
    except (ValueError, TypeError):
        return default


_TRUTHY = {"true", "yes", "1", "ja", "on"}


def safe_bool(value) -> bool:
    """Konvertiert Input zu bool. String-Vergleich case-insensitive."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    try:
        return str(value).strip().lower() in _TRUTHY
    except Exception:  # noqa: BLE001
        return False
