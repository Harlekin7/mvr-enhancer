"""MVR Enhancer — Vectorworks-MVR nach grandMA3 aufbereiten.

Der Import dieses Pakets haertet als Seiteneffekt die XML-Stdlib
(``defusedxml.defuse_stdlib()``). Das ist bewusst hier verankert und nicht
in ``main.run()``: unser eigener MVR-Reader nutzt bereits ``defusedxml``
direkt, aber ``pygdtf`` parst ``description.xml`` mit dem ungeschuetzten
``xml.etree.ElementTree`` — eine praeparierte ``.gdtf`` aus einem
Bibliotheksordner oder einem MVR koennte damit per Entity-Expansion
("Billion Laughs") den Prozess sprengen. Da jeder Einstiegspunkt (Fenster,
``__main__``, Tests, Bibliotheks-Scan) ueber ein ``mvr_enhancer``-Import
laeuft, greift der Schutz hier ueberall.
"""

__version__ = "0.3.0"

try:
    import warnings as _warnings

    import defusedxml as _defusedxml

    with _warnings.catch_warnings():
        # defuse_stdlib() importiert intern das (in defusedxml selbst)
        # deprecated cElementTree-Modul — die Warnung ist nichts, was ein
        # Aufrufer dieses Pakets beheben koennte.
        _warnings.simplefilter("ignore", DeprecationWarning)
        _defusedxml.defuse_stdlib()
except ImportError:  # pragma: no cover — defusedxml ist eine harte Dependency
    import logging

    logging.getLogger(__name__).warning(
        "defusedxml nicht verfuegbar — XML-Parsing ist NICHT gegen "
        "Entity-Expansion geschuetzt."
    )
