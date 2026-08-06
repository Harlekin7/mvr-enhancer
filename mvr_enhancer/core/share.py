"""GDTF Share API-Client: Login, gecachte Fixture-Liste, Suche, Download.

Portiert aus vw-tool-gpa ``app/vectorwatch/parsing/gdtf.py`` (Z. 376-539).

Dies ist bewusst das einzige Netzwerk-Modul der Anwendung — die UI selbst
hat keinen Netzwerkzugriff, ``GdtfShareClient`` ist die eine Ausnahme.
Saemtliche HTTP-Kommunikation laeuft durch die einzige Naht-Methode
``_request()``, damit Tests das Netzwerk vollstaendig durch Monkeypatching
ersetzen koennen, ohne tiefer in urllib eingreifen zu muessen.
"""

import json
import logging
import os
import ssl
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from http.cookiejar import CookieJar

from mvr_enhancer.core.constants import MAX_GDTF_DOWNLOAD_SIZE
from mvr_enhancer.core.gdtf import GdtfFixture, import_gdtf, parse_gdtf, token_match

log = logging.getLogger(__name__)

GDTF_SHARE_BASE = "https://gdtf-share.com/apis/public"


class GdtfShareClient:
    """Client fuer die GDTF Share REST-API (Login, Liste, Suche, Download)."""

    def __init__(self, cache_path: str | None = None):
        self._lock = threading.Lock()
        self._cookie_jar = CookieJar()
        ssl_ctx = ssl.create_default_context()
        # PyInstaller-Frozen: certifi-Zertifikate verwenden falls verfuegbar.
        try:
            import certifi
            ssl_ctx.load_verify_locations(certifi.where())
        except ImportError:
            pass
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cookie_jar),
            urllib.request.HTTPSHandler(context=ssl_ctx),
        )
        self.logged_in = False
        self.last_error: str = ""
        self._username: str = ""
        self._password: str = ""
        self._fixture_list: list[dict] | None = None
        self._cache_path = cache_path

    # ──── Netzwerk-Naht ────

    def _request(
        self,
        method: str,
        slug: str,
        params: dict | None = None,
        data: dict | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> tuple[int, bytes, str]:
        """Fuehrt einen HTTP-Request gegen die GDTF Share API aus.

        Einzige tatsaechliche Netzwerk-I/O-Stelle des Clients — Tests
        ersetzen ausschliesslich diese Methode via monkeypatch. Gibt
        ``(status_code, body_bytes, content_disposition)`` zurueck; ein
        ``HTTPError`` wird abgefangen und ebenfalls als
        ``(code, body, content_disposition)`` zurueckgegeben, damit Aufrufer
        nur einen Fehlerpfad (Statuscode-Pruefung) behandeln muessen statt
        zwei (Exception vs. Rueckgabewert).

        ``content_disposition`` ist bewusst Teil des Rueckgabewerts und wird
        NICHT auf der Instanz zwischengespeichert: der Header gehoert zu
        genau dieser Antwort. Als Instanz-Attribut (fruehere Fassung:
        ``self._last_content_disposition``) war er ein Seitenkanal, ueber den
        sich zwei parallele Downloads gegenseitig den Zieldateinamen
        ueberschreiben und damit das falsche GDTF unter dem Namen des
        anderen in die Bibliothek legen konnten.

        Liest die Antwort in 64-KiB-Chunks und bricht das Lesen ab, sobald
        ``MAX_GDTF_DOWNLOAD_SIZE`` ueberschritten ist (Schutz vor
        unbegrenztem Speicherverbrauch bei sehr grossen Antworten). Die
        endgueltige Entscheidung ueber "zu gross" trifft ``download()``
        anhand der zurueckgegebenen Bytes selbst, damit dieser Schutz auch
        bei gemockten Requests in Tests greift.

        Bei ``data`` (Form-POST) wird ``Content-Type:
        application/x-www-form-urlencoded`` explizit gesetzt. CPython's
        ``AbstractHTTPHandler.do_request_`` wuerde diesen Header ohnehin
        automatisch ergaenzen, wenn er fehlt (``Lib/urllib/request.py``,
        ``do_request_``); er wird hier trotzdem explizit gesetzt, damit das
        Verhalten unabhaengig vom Handler-Verhalten selbsterklaerend bleibt.

        ``progress``, falls gesetzt, wird nach jedem gelesenen Chunk mit
        ``(downloaded_bytes, total_bytes)`` aufgerufen; ``total_bytes`` stammt
        aus dem ``Content-Length``-Header der Antwort und ist ``0``, wenn er
        fehlt oder nicht parsbar ist (unbekannte Gesamtgroesse).
        """
        url = f"{GDTF_SHARE_BASE}/{slug}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        headers = (
            {"Content-Type": "application/x-www-form-urlencoded"} if body is not None else {}
        )
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=30) as resp:
                disposition = resp.headers.get("Content-Disposition", "")
                try:
                    total_bytes = int(resp.headers.get("Content-Length") or 0)
                except ValueError:
                    total_bytes = 0
                chunks = []
                downloaded = 0
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    downloaded += len(chunk)
                    if progress is not None:
                        progress(downloaded, total_bytes)
                    if downloaded > MAX_GDTF_DOWNLOAD_SIZE:
                        break
                return resp.status, b"".join(chunks), disposition
        except urllib.error.HTTPError as e:
            disposition = e.headers.get("Content-Disposition", "") if e.headers else ""
            return e.code, e.read(), disposition

    def _extract_error(self, status: int, body: bytes) -> str | None:
        """Extrahiert ein ``error``-Feld aus einer JSON-Fehlerantwort, falls vorhanden."""
        try:
            data = json.loads(body.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if isinstance(data, dict) and "error" in data:
            return str(data["error"])
        return None

    # ──── Login ────

    def login(self, username: str, password: str) -> bool:
        """Authentifiziert beim GDTF Share. Gibt True bei Erfolg zurueck."""
        with self._lock:
            self._username = username
            self._password = password
            return self._do_login()

    def _do_login(self) -> bool:
        """Fuehrt den Login-Request durch.

        Achtung: Muss unter self._lock aufgerufen werden.
        """
        self.last_error = ""
        try:
            status, resp_body, _disposition = self._request(
                "POST",
                "login.php",
                data={"user": self._username, "password": self._password},
            )
        except OSError as e:
            self.logged_in = False
            self.last_error = str(e)
            log.warning("GDTF Share Login fehlgeschlagen: %s", e)
            return False

        if status != 200:
            self.logged_in = False
            self.last_error = self._extract_error(status, resp_body) or f"HTTP {status}"
            log.warning("GDTF Share Login fehlgeschlagen: %s", self.last_error)
            return False

        try:
            data = json.loads(resp_body.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self.logged_in = False
            self.last_error = str(e)
            log.warning("GDTF Share Login-Antwort ungueltig: %s", e)
            return False

        self.logged_in = data.get("result") is True
        if not self.logged_in:
            self.last_error = data.get("error", "Login fehlgeschlagen")
        return self.logged_in

    def _relogin(self) -> bool:
        """Erneuert die Session nach Cookie-Timeout (~2h)."""
        with self._lock:
            if not self._username or not self._password:
                return False
            log.info("GDTF Share Session abgelaufen, erneuere Login...")
            return self._do_login()

    def logout(self) -> None:
        """Beendet die Session lokal (verwirft Cookies, Zugangsdaten und Listen-Cache)."""
        with self._lock:
            self.logged_in = False
            self._username = ""
            self._password = ""
            self._cookie_jar.clear()
            self._fixture_list = None

    # ──── Fixture-Liste ────

    def get_fixture_list(
        self, force_refresh: bool = False, *, allow_retry: bool = True,
    ) -> list[dict]:
        """Ruft die komplette Fixture-Liste vom GDTF Share ab (gecacht).

        Ohne ``force_refresh`` wird zuerst der In-Memory-Cache, dann ein
        etwaiger Disk-Cache (``cache_path``) genutzt, bevor das Netzwerk
        kontaktiert wird. ``force_refresh=True`` erzwingt einen Netz-Request.

        ``allow_retry`` steuert den einmaligen Relogin-Versuch nach HTTP 401
        und ist bewusst ein Parameter statt eines Instanz-Attributs (fruehere
        Fassung: ``self._retry_active``): als geteilter Zustand haette ein
        paralleler Aufruf den Relogin-Schutz des anderen zuruecksetzen oder
        dessen legitimen Retry unterdruecken koennen.
        """
        if not force_refresh:
            if self._fixture_list is not None:
                return self._fixture_list
            cached = self._read_list_cache()
            if cached is not None:
                self._fixture_list = cached
                return cached

        if not self.logged_in:
            return []

        self.last_error = ""
        try:
            status, body, _disposition = self._request("GET", "getList.php")
        except OSError as e:
            self.last_error = str(e)
            log.warning("GDTF Share Liste konnte nicht abgerufen werden: %s", e)
            return []

        if status == 401 and allow_retry:
            if self._relogin():
                return self.get_fixture_list(force_refresh=True, allow_retry=False)
            self.last_error = "Session abgelaufen, Relogin fehlgeschlagen"
            return []

        if status != 200:
            self.last_error = self._extract_error(status, body) or f"HTTP {status}"
            log.warning("GDTF Share Liste konnte nicht abgerufen werden: %s", self.last_error)
            return []

        try:
            data = json.loads(body.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self.last_error = str(e)
            log.warning("GDTF Share Liste konnte nicht abgerufen werden: %s", e)
            return []

        if not data.get("result", True) and "error" in data:
            self.last_error = data["error"]
            log.warning("GDTF Share Serverfehler: %s", data["error"])
            return []

        self._fixture_list = data.get("list", [])
        self._write_list_cache(self._fixture_list)
        return self._fixture_list

    def _read_list_cache(self) -> list[dict] | None:
        """Laedt die gecachte Fixture-Liste von ``cache_path``, falls vorhanden."""
        if not self._cache_path or not os.path.isfile(self._cache_path):
            return None
        try:
            with open(self._cache_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("list")
        except (OSError, json.JSONDecodeError, AttributeError) as e:
            log.warning("GDTF Share Listen-Cache konnte nicht gelesen werden: %s", e)
            return None

    def _write_list_cache(self, fixture_list: list[dict]) -> None:
        """Schreibt die Fixture-Liste atomar nach ``cache_path`` (falls gesetzt)."""
        if not self._cache_path:
            return
        payload = {"timestamp": time.time(), "list": fixture_list}
        cache_dir = os.path.dirname(self._cache_path) or "."
        try:
            os.makedirs(cache_dir, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f)
                os.replace(tmp_path, self._cache_path)
            except OSError:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as e:
            log.warning("GDTF Share Listen-Cache konnte nicht geschrieben werden: %s", e)

    # ──── Suche ────

    def search(self, query: str, limit: int = 50) -> list[dict]:
        """Durchsucht die Fixture-Liste (client-seitig, token-basiert)."""
        if self._fixture_list is None:
            self.get_fixture_list()

        if not self._fixture_list:
            return []
        self.last_error = ""

        results = []
        for item in self._fixture_list:
            combined = f"{item.get('manufacturer', '')} {item.get('fixture', '')}"
            if token_match(query, combined):
                results.append(item)

        return results[:limit]

    # ──── Download ────

    def download(
        self,
        rid: int,
        library_dir: str,
        *,
        allow_retry: bool = True,
        progress: Callable[[int, int], None] | None = None,
    ) -> GdtfFixture | None:
        """Laedt eine Fixture-Datei herunter und importiert sie in die Bibliothek.

        Die Bytes landen zuerst unter einem ``.part``-Namen und werden erst
        nach erfolgreichem Parsen per ``os.replace`` auf den Zielnamen
        gezogen: ein defekter Download darf keine unbrauchbare Datei in der
        Bibliothek hinterlassen, an der jeder spaetere Scan erneut scheitert.

        ``allow_retry`` steuert (wie in ``get_fixture_list``) den einmaligen
        Relogin nach HTTP 401 als reiner Aufruf-Zustand. Der Download laeuft
        bewusst NICHT unter ``self._lock``: ``_relogin()`` nimmt denselben
        Lock und wuerde sich selbst blockieren.

        ``progress`` wird ausschliesslich an den eigentlichen Download-
        Request durchgereicht — nicht an einen etwaigen Relogin-Request:
        dessen Antwort hat keinen fuer die UI relevanten Fortschritt.
        """
        if not self.logged_in:
            self.last_error = "Nicht eingeloggt"
            return None

        os.makedirs(library_dir, exist_ok=True)
        self.last_error = ""

        try:
            status, body, disposition = self._request(
                "GET", "downloadFile.php", params={"rid": rid}, progress=progress,
            )
        except OSError as e:
            self.last_error = str(e)
            log.warning("GDTF Download fehlgeschlagen (rid=%d): %s", rid, e)
            return None

        if status == 401 and allow_retry:
            if self._relogin():
                return self.download(rid, library_dir, allow_retry=False, progress=progress)
            self.last_error = "Session abgelaufen, Relogin fehlgeschlagen"
            return None

        if status != 200:
            self.last_error = self._extract_error(status, body) or f"HTTP {status}"
            log.warning("GDTF Download fehlgeschlagen (rid=%d): %s", rid, self.last_error)
            return None

        if len(body) > MAX_GDTF_DOWNLOAD_SIZE:
            self.last_error = (
                f"Download-Groessenlimit ueberschritten "
                f"(>{MAX_GDTF_DOWNLOAD_SIZE // 1_000_000} MB)"
            )
            log.warning("GDTF Download abgebrochen (rid=%d): %s", rid, self.last_error)
            return None

        filename = self._filename_for_download(rid, disposition)
        dest = os.path.join(library_dir, filename)
        tmp_dest = f"{dest}.part"

        try:
            with open(tmp_dest, "wb") as f:
                f.write(body)
        except OSError as e:
            self.last_error = str(e)
            log.warning("GDTF Download konnte nicht gespeichert werden (rid=%d): %s", rid, e)
            self._discard(tmp_dest)
            return None

        # Erst validieren, dann veroeffentlichen.
        if parse_gdtf(tmp_dest) is None:
            self.last_error = "GDTF-Datei konnte nicht importiert werden"
            log.warning(
                "GDTF Download unbrauchbar, verworfen (rid=%d): %s", rid, filename,
            )
            self._discard(tmp_dest)
            return None

        try:
            os.replace(tmp_dest, dest)
        except OSError as e:
            self.last_error = str(e)
            log.warning("GDTF Download konnte nicht gespeichert werden (rid=%d): %s", rid, e)
            self._discard(tmp_dest)
            return None

        # import_gdtf() parst erneut — diesmal unter dem endgueltigen Namen,
        # aus dem die Revision abgeleitet wird — und schreibt den JSON-Cache.
        fixture = import_gdtf(dest, library_dir)
        if fixture is None:
            self.last_error = "GDTF-Datei konnte nicht importiert werden"
            self._discard(dest)
            return None
        return fixture

    @staticmethod
    def _discard(path: str) -> None:
        """Loescht eine (Zwischen-)Datei; Fehler beim Loeschen sind nicht fatal."""
        try:
            os.unlink(path)
        except OSError as e:
            log.debug("Temporaere Download-Datei konnte nicht entfernt werden: %s", e)

    @staticmethod
    def _filename_for_download(rid: int, content_disposition: str = "") -> str:
        """Bestimmt den Zieldateinamen aus Content-Disposition oder einem Fallback.

        ``content_disposition`` wird als Parameter uebergeben (nicht von der
        Instanz gelesen), damit der Name eindeutig zur jeweiligen Antwort
        gehoert — siehe ``_request``.
        """
        cd = content_disposition or ""
        if "filename=" in cd:
            filename = cd.split("filename=")[-1].strip('" ')
            filename = os.path.basename(filename.replace("\\", "/"))  # Traversal
            if filename:
                return filename
        return f"fixture_{rid}.gdtf"
