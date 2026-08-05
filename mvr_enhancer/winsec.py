"""Windows-Plattform-Utilities — DPAPI-Credentials.

Sichere Passwortspeicherung ueber Windows Data Protection API (DPAPI).

Portiert aus vw-tool-gpa ``app/vectorwatch/win_platform.py`` (Z. 67-99).
Auf Nicht-Windows-Plattformen ist DPAPI nicht verfuegbar; die
oeffentlichen Funktionen werfen dort ``ValueError``.
"""

import base64
import logging
import sys

log = logging.getLogger(__name__)


def _require_windows() -> None:
    if sys.platform != "win32":
        raise ValueError("DPAPI ist nur unter Windows verfuegbar")


def _ensure_ctypes():
    """Importiert ctypes-Module lazy, damit das Modul auf allen Plattformen ladbar bleibt."""
    import ctypes
    import ctypes.wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    return ctypes, DataBlob


def _encrypt_dpapi(data: bytes) -> bytes:
    """Verschluesselt Bytes mit Windows DPAPI."""
    ctypes, DataBlob = _ensure_ctypes()
    blob_in = DataBlob(len(data), ctypes.cast(
        ctypes.create_string_buffer(data, len(data)),
        ctypes.POINTER(ctypes.c_char)))
    blob_out = DataBlob()

    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptProtectData fehlgeschlagen")

    try:
        encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        if blob_out.pbData:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return encrypted


def _decrypt_dpapi(data: bytes) -> bytes:
    """Entschluesselt Bytes mit Windows DPAPI."""
    ctypes, DataBlob = _ensure_ctypes()
    blob_in = DataBlob(len(data), ctypes.cast(
        ctypes.create_string_buffer(data, len(data)),
        ctypes.POINTER(ctypes.c_char)))
    blob_out = DataBlob()

    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptUnprotectData fehlgeschlagen")

    try:
        decrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        if blob_out.pbData:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return decrypted


def encrypt_password(password: str) -> str:
    """Verschluesselt ein Passwort und gibt es als Base64-String zurueck.

    Format: 'dpapi:' + Base64-kodierte verschluesselte Daten.
    Leere Eingabe ergibt einen leeren String (kein Fehler).
    Auf Nicht-Windows-Plattformen wird ``ValueError`` geworfen.
    """
    _require_windows()
    if not password:
        return ""
    try:
        encrypted = _encrypt_dpapi(password.encode("utf-8"))
        return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
    except OSError:
        log.error("DPAPI-Verschluesselung fehlgeschlagen — Passwort wird nicht gespeichert")
        return ""


def decrypt_password(stored: str) -> str:
    """Entschluesselt ein gespeichertes Passwort.

    Erkennt das 'dpapi:'-Praefix und entschluesselt entsprechend.
    Klartext-Passwoerter (ohne Praefix) werden abgelehnt.
    Auf Nicht-Windows-Plattformen wird ``ValueError`` geworfen.
    """
    _require_windows()
    if not stored:
        return ""
    if not stored.startswith("dpapi:"):
        log.error("Unverschluesseltes Passwort in Config gefunden [REDACTED] — "
                  "wird ignoriert. Bitte Passwort neu eingeben.")
        return ""
    try:
        encrypted = base64.b64decode(stored[6:])
        return _decrypt_dpapi(encrypted).decode("utf-8")
    except (OSError, ValueError) as e:
        log.warning("DPAPI-Entschluesselung fehlgeschlagen: %s", type(e).__name__)
        return ""
