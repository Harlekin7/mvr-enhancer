"""Zentrale Modul-Konstanten für MVR-/GDTF-Limits.

Portiert aus vw-tool-gpa `vectorwatch/constants.py` (Zeilen 31-39).
"""

# === MVR-Limits ===
# MAX_MVR_EMBEDDED_FILE_COUNT und MAX_MVR_TOTAL_EXTRACTED wurden angehoben,
# nachdem ein reales Vectorworks-MVR ("26-0046_EverSo_TBFTC V4.mvr", ~988
# eingebettete Mesh-Dateien) am alten Limit von 1000 gescheitert ist und
# Geometrie stillschweigend verworfen hat — echte Shows koennen legitim mehr
# als 1000 eingebettete Eintraege haben. MAX_MVR_EMBEDDED_FILE_SIZE (pro
# Datei) und MAX_MVR_XML_SIZE bleiben unveraendert; zusammen mit dem weiterhin
# begrenzten MAX_MVR_TOTAL_EXTRACTED bilden sie weiterhin den eigentlichen
# Schutz vor Zip-Bomben (viele kleine Dateien koennen in Summe nicht mehr
# Bytes ergeben, als das Gesamtlimit erlaubt).
MAX_MVR_XML_SIZE: int = 500_000_000           # 500 MB
MAX_MVR_EMBEDDED_FILE_SIZE: int = 100_000_000  # 100 MB pro Datei
MAX_MVR_TOTAL_EXTRACTED: int = 2 * 1024 * 1024 * 1024  # 2 GB gesamt (Zip-Bomb-Schutz)
MAX_MVR_EMBEDDED_FILE_COUNT: int = 20_000     # Max Dateien pro Archiv (reale Shows > 1000)

# === GDTF-Limits ===
MAX_GDTF_FILE_SIZE: int = 200_000_000   # 200 MB — lokale GDTF-Datei
MAX_GDTF_DOWNLOAD_SIZE: int = 200_000_000  # 200 MB — GDTF Share API Download
