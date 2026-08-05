"""Zentrale Modul-Konstanten für MVR-/GDTF-Limits.

Portiert aus vw-tool-gpa `vectorwatch/constants.py` (Zeilen 31-39).
"""

# === MVR-Limits ===
MAX_MVR_XML_SIZE: int = 500_000_000           # 500 MB
MAX_MVR_EMBEDDED_FILE_SIZE: int = 100_000_000  # 100 MB pro Datei
MAX_MVR_TOTAL_EXTRACTED: int = 500_000_000    # 500 MB gesamt
MAX_MVR_EMBEDDED_FILE_COUNT: int = 1000       # Max Dateien pro Archiv

# === GDTF-Limits ===
MAX_GDTF_FILE_SIZE: int = 200_000_000   # 200 MB — lokale GDTF-Datei
MAX_GDTF_DOWNLOAD_SIZE: int = 200_000_000  # 200 MB — GDTF Share API Download
