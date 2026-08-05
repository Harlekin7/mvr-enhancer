"""MVR-Enricher — reichert eine gelesene MVR-Szene typ-basiert an.

Ordnet jede Fixture-Instanz ueber ``_normalize(fixture.name)`` einem
``Assignment`` (Task 6) zu, aktualisiert GDTFSpec/GDTFMode/Addresses,
entfernt problematische Elemente (``CustomCommands``, ``Position``),
baut den Export-Baum neu auf (ein Layer, optional Positions-Gruppen)
und schreibt ein neues MVR-ZIP — dabei werden verwaiste, nicht mehr
referenzierte eingebettete GDTFs verworfen, Meshes bleiben unangetastet.

Portierungsquelle: ``mvr_enricher.py`` (VectorWatch-Tool). Uebernommen:
``_STRIP_TAGS``, ``_clean_gdtf_name``, ``_update_fixture_element``,
``_reorganize_layers`` (Grundstruktur), reproduzierbare UUIDs via
``uuid5(NAMESPACE_DNS, seed)``. Neu in dieser Portierung: kein
``Fixture``/``_match_fixtures`` mehr (Zuordnung laeuft ueber
``assignments[type_key]`` statt Namens-/DMX-Matching), sowie die
Orphan-GDTF-Bereinigung und der strukturierte ``EnrichReport``.
"""

import io
import logging
import os
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, OrderedDict

from mvr_enhancer.core.analysis import (
    _MESH_EXTENSIONS,
    _build_layer_map,
    _resolve_position,
    parse_position_names,
)
from mvr_enhancer.core.gdtf import GdtfFixture, GdtfMode, _normalize, find_gdtf_file
from mvr_enhancer.core.models import (
    Assignment,
    CleanupSummary,
    EnrichReport,
    EnrichResult,
    FixtureType,
    ModeFallbackWarning,
)
from mvr_enhancer.core.mvr_reader import MvrFixture, MvrScene

log = logging.getLogger(__name__)

_NS = uuid.NAMESPACE_DNS

# Identity-Matrix im MVR-Textformat (3 Zeilen: Rotation/Translation, keine
# vierte {0,0,0,1}-Zeile — analog zur Portierungsquelle).
_IDENTITY_MATRIX = "{1,0,0,0}{0,1,0,0}{0,0,1,0}"

_LAYER_NAME = "MVR Enhancer Export"

# Problematische MVR-Element-Tags, die beim Export entfernt werden:
# CustomCommands (VW schreibt ein fuer MA3 ungueltiges Format) und
# Position (referenziert haeufig UUIDs ohne Definitions-Block).
_STRIP_TAGS = {"CustomCommands", "Position"}


def _clean_gdtf_name(name: str) -> str:
    """URL-dekodiert GDTF-Dateinamen (%40 -> @ etc.)."""
    decoded = urllib.parse.unquote(name)
    return decoded.replace("%40", "@")


def _gdtf_ref_keys(spec_text: str) -> set[str]:
    """Baut Vergleichsschluessel fuer einen ``GDTFSpec``-Wert.

    Liefert den dekodierten Namen sowohl mit als auch ohne ``.gdtf``-Endung,
    damit Referenzen unabhaengig davon erkannt werden, ob eine Datei mit
    oder ohne Endung benannt ist.
    """
    decoded = _clean_gdtf_name(spec_text)
    if decoded.lower().endswith(".gdtf"):
        base = decoded[: -len(".gdtf")]
    else:
        base = decoded
    return {decoded, base, f"{base}.gdtf"}


def _strip_nonstandard_elements(element: ET.Element, counts: Counter) -> None:
    """Entfernt ``_STRIP_TAGS``-Kinder aus einem Fixture-Element und zaehlt sie."""
    to_remove = [child for child in element if child.tag in _STRIP_TAGS]
    for child in to_remove:
        element.remove(child)
        counts[child.tag] += 1


def _update_fixture_element(
    element: ET.Element,
    fixture: MvrFixture,
    gdtf_filename: str,
    gdtf_mode_name: str,
) -> None:
    """Aktualisiert ein Fixture-XML-Element mit der finalen Zuordnung.

    Matrix wird nicht angefasst (3D-Position aus dem Quell-MVR bleibt
    erhalten). Die DMX-Adresse stammt direkt aus ``fixture.dmx_address``
    (bereits absolut, wie vom MVR-Reader geliefert) — es wird hier nicht
    neu berechnet, nur das Element in normalisierter Form sichergestellt.
    """
    if gdtf_filename:
        gdtf_spec_el = element.find("GDTFSpec")
        if gdtf_spec_el is None:
            gdtf_spec_el = ET.SubElement(element, "GDTFSpec")
        gdtf_spec_el.text = gdtf_filename

    if gdtf_mode_name:
        gdtf_mode_el = element.find("GDTFMode")
        if gdtf_mode_el is None:
            gdtf_mode_el = ET.SubElement(element, "GDTFMode")
        gdtf_mode_el.text = gdtf_mode_name

    addresses_el = element.find("Addresses")
    if addresses_el is None:
        addresses_el = ET.SubElement(element, "Addresses")
    addr_el = addresses_el.find("Address")
    if addr_el is None:
        addr_el = ET.SubElement(addresses_el, "Address")
    addr_el.set("break", "0")
    addr_el.text = str(fixture.dmx_address)

    # FixtureID/UnitNumber: dieses Tool kennt kein eigenes Kanal-/Unit-Datenmodell
    # (anders als die Portierungsquelle mit ihrer internen Fixture-Liste) —
    # bestehende Werte aus dem Quell-MVR bleiben daher unangetastet, es wird
    # nur sichergestellt, dass die Elemente ueberhaupt vorhanden sind.
    if element.find("FixtureID") is None:
        fixture_id_el = ET.SubElement(element, "FixtureID")
        fixture_id_el.text = "0"

    if element.find("UnitNumber") is None:
        unit_el = ET.SubElement(element, "UnitNumber")
        unit_el.text = "0"


def _resolve_mode_name(vw_mode: str, modes: list[GdtfMode]) -> str:
    """Bestimmt den GDTF-Modus per Substring-Abgleich, sonst ``modes[0]``."""
    vw_mode_lower = (vw_mode or "").lower()
    if vw_mode_lower:
        for mode in modes:
            mode_lower = mode.name.lower()
            if vw_mode_lower in mode_lower or mode_lower in vw_mode_lower:
                return mode.name
    return modes[0].name


def _reorganize_layers(
    scene: MvrScene,
    kept_fixtures: list[MvrFixture],
    group_by_position: bool,
) -> tuple[ET.Element, int]:
    """Baut den XML-Baum mit Layer- und Gruppen-Struktur neu auf.

    Gibt das neue Root-Element und die Anzahl gebildeter Positions-Gruppen
    zurueck (0, wenn ``group_by_position=False``).
    """
    root = ET.Element("GeneralSceneDescription")
    root.set("verMajor", "1")
    root.set("verMinor", "5")
    root.set("provider", "MVR Enhancer")

    if scene.user_data is not None:
        root.append(scene.user_data)

    scene_el = ET.SubElement(root, "Scene")
    layers_el = ET.SubElement(scene_el, "Layers")

    layer = ET.SubElement(layers_el, "Layer")
    layer.set("uuid", str(uuid.uuid5(_NS, f"layer_{_LAYER_NAME}")))
    layer.set("name", _LAYER_NAME)
    layer_matrix = ET.SubElement(layer, "Matrix")
    layer_matrix.text = _IDENTITY_MATRIX
    child_list = ET.SubElement(layer, "ChildList")

    position_group_count = 0
    if group_by_position:
        position_names = parse_position_names(scene)
        layer_map = _build_layer_map(scene)

        position_groups: OrderedDict[str, list[ET.Element]] = OrderedDict()
        for fixture in kept_fixtures:
            pos = _resolve_position(fixture, position_names, layer_map)
            position_groups.setdefault(pos, []).append(fixture.element)

        for pos_name, elements in position_groups.items():
            group = ET.SubElement(child_list, "GroupObject")
            group.set("uuid", str(uuid.uuid5(_NS, f"group_{pos_name}")))
            group.set("name", pos_name)
            group_matrix = ET.SubElement(group, "Matrix")
            group_matrix.text = _IDENTITY_MATRIX
            group_cl = ET.SubElement(group, "ChildList")
            for el in elements:
                group_cl.append(el)

        position_group_count = len(position_groups)
    else:
        for fixture in kept_fixtures:
            child_list.append(fixture.element)

    if scene.non_fixture_elements:
        group_3d = ET.SubElement(child_list, "GroupObject")
        group_3d.set("uuid", str(uuid.uuid5(_NS, "group_3D")))
        group_3d.set("name", "3D")
        group_3d_matrix = ET.SubElement(group_3d, "Matrix")
        group_3d_matrix.text = _IDENTITY_MATRIX
        group_3d_cl = ET.SubElement(group_3d, "ChildList")
        for el in scene.non_fixture_elements:
            group_3d_cl.append(el)

    if scene.aux_data is not None:
        scene_el.append(scene.aux_data)

    return root, position_group_count


def enrich_mvr(
    scene: MvrScene,
    types: list[FixtureType],
    assignments: dict[str, Assignment],
    gdtf_library_dir: str,
    gdtf_library: dict[str, GdtfFixture],
    group_by_position: bool = True,
) -> EnrichResult:
    """Reichert ``scene`` typ-basiert an und liefert ein neues MVR-ZIP + Report.

    Jede Fixture-Instanz wird ueber ``_normalize(fixture.name)`` einem
    ``Assignment`` zugeordnet. Fehlt die Zuordnung (``assignments.get(key)
    is None``) oder ist sie explizit ``removed=True``, wird die Instanz aus
    dem Export entfernt. Fuer jeden verbleibenden Typ wird die GDTF-Datei
    ueber die Bibliothek aufgeloest und eingebettet, der Modus bestimmt
    (Override -> Substring-Match -> ``modes[0]``, mit Fallback-Report) und
    das Fixture-Element aktualisiert. Nicht mehr referenzierte eingebettete
    ``.gdtf``-Dateien werden verworfen; alle anderen eingebetteten Dateien
    (Meshes etc.) bleiben unveraendert erhalten.
    """
    type_by_key = {t.key: t for t in types}

    # 1. Fixtures klassifizieren: behalten vs. verwerfen.
    kept_fixtures: list[MvrFixture] = []
    dropped_count = 0
    for fixture in scene.fixtures:
        key = _normalize(fixture.name)
        assignment = assignments.get(key)
        # Dropped when there's no assignment at all, the type is unassigned
        # (gdtf_name is None — e.g. a still-open UI row), or it was
        # explicitly marked removed (e.g. a plugbox/distro with no GDTF).
        if assignment is None or assignment.gdtf_name is None or assignment.removed:
            dropped_count += 1
            continue
        kept_fixtures.append(fixture)

    removed_type_names = [
        t.name
        for t in types
        if (a := assignments.get(t.key)) is not None and a.removed
    ]

    # 2. Pro verbleibendem Typ: GDTF-Datei + Modus aufloesen.
    fixtures_by_type: dict[str, list[MvrFixture]] = {}
    for fixture in kept_fixtures:
        fixtures_by_type.setdefault(_normalize(fixture.name), []).append(fixture)

    gdtf_paths: dict[str, str] = {}  # zip_name -> abs. Pfad in der Bibliothek
    type_gdtf_filename: dict[str, str] = {}
    type_mode_name: dict[str, str] = {}
    fallbacks: list[ModeFallbackWarning] = []

    for key, fixtures_of_type in fixtures_by_type.items():
        assignment = assignments[key]
        matched = gdtf_library.get(assignment.gdtf_name) if assignment.gdtf_name else None

        zip_name = ""
        abs_path = find_gdtf_file(
            assignment.gdtf_name or "", gdtf_library_dir, gdtf_library, {}, matched=matched,
        )
        if abs_path and os.path.isfile(abs_path):
            zip_name = _clean_gdtf_name(os.path.basename(abs_path))
            gdtf_paths[zip_name] = abs_path
        type_gdtf_filename[key] = zip_name

        if assignment.mode_name:
            mode_name = assignment.mode_name
        else:
            mode_name = ""
            if matched is not None and matched.modes:
                fixture_type = type_by_key.get(key)
                existing_mode = fixture_type.existing_mode if fixture_type else ""
                mode_name = _resolve_mode_name(existing_mode, matched.modes)
                fallbacks.append(
                    ModeFallbackWarning(
                        type_name=fixture_type.name if fixture_type else fixtures_of_type[0].name,
                        count=len(fixtures_of_type),
                        gdtf_name=assignment.gdtf_name or "",
                        mode_name=mode_name,
                    )
                )
        type_mode_name[key] = mode_name

    # 3. Fixture-Elemente aktualisieren (GDTFSpec/GDTFMode/Addresses/...).
    #    Wichtig: das Stripping von <Position> (Schritt 4b) muss erst NACH
    #    dem Baum-Aufbau (Schritt 4a) erfolgen, da die Positions-Gruppierung
    #    (via analysis._resolve_position) genau dieses Element noch liest.
    for fixture in kept_fixtures:
        key = _normalize(fixture.name)
        _update_fixture_element(
            fixture.element,
            fixture,
            type_gdtf_filename.get(key, ""),
            type_mode_name.get(key, ""),
        )

    # 4a. Neuen XML-Baum aufbauen (liest <Position> fuer die Gruppierung).
    root, position_group_count = _reorganize_layers(scene, kept_fixtures, group_by_position)

    # 4b. Nicht-standardkonforme Elemente entfernen und verbliebene
    #     URL-kodierte GDTFSpec-Werte dekodieren.
    stripped_counts: Counter = Counter()
    for fixture in kept_fixtures:
        _strip_nonstandard_elements(fixture.element, stripped_counts)

        gdtf_el = fixture.element.find("GDTFSpec")
        if gdtf_el is not None and gdtf_el.text and "%" in gdtf_el.text:
            gdtf_el.text = _clean_gdtf_name(gdtf_el.text)

    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)
    xml_buf = io.BytesIO()
    tree.write(xml_buf, encoding="UTF-8", xml_declaration=True)
    xml_data = xml_buf.getvalue()

    # 5. Referenz-Set aller finalen GDTFSpec-Werte bilden (fuer Orphan-Check).
    reference_keys: set[str] = set()
    for fixture in kept_fixtures:
        gdtf_el = fixture.element.find("GDTFSpec")
        if gdtf_el is not None and gdtf_el.text:
            reference_keys |= _gdtf_ref_keys(gdtf_el.text)

    # 6. ZIP schreiben: referenzierte/zugeordnete GDTFs + alle Nicht-GDTF-Dateien.
    orphan_names: list[str] = []
    mesh_count = 0
    written_gdtf_names: set[str] = set()

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("GeneralSceneDescription.xml", xml_data)

        for name, data in scene.embedded_files.items():
            if name.lower().endswith(".gdtf"):
                clean_name = _clean_gdtf_name(name)
                if clean_name in gdtf_paths:
                    # Wird weiter unten durch unsere aufgeloeste Bibliotheks-
                    # Datei ersetzt (gleicher Ziel-Dateiname).
                    continue
                if clean_name in reference_keys:
                    zf.writestr(clean_name, data)
                    written_gdtf_names.add(clean_name)
                else:
                    orphan_names.append(clean_name)
            else:
                zf.writestr(name, data)
                if os.path.splitext(name)[1].lower() in _MESH_EXTENSIONS:
                    mesh_count += 1

        for zip_name, abs_path in gdtf_paths.items():
            zf.write(abs_path, zip_name)
            written_gdtf_names.add(zip_name)

    log.info(
        "MVR angereichert: %d/%d Fixtures exportiert (%d entfernt), "
        "%d GDTFs eingebettet, %d verwaiste GDTFs entfernt, %d Positionsgruppen",
        len(kept_fixtures), len(scene.fixtures), dropped_count,
        len(written_gdtf_names), len(orphan_names), position_group_count,
    )

    report = EnrichReport(
        matched_fixtures=len(kept_fixtures),
        total_fixtures=len(scene.fixtures),
        embedded_gdtf_count=len(written_gdtf_names),
        mesh_count=mesh_count,
        position_group_count=position_group_count,
        fallbacks=fallbacks,
        cleanup=CleanupSummary(
            removed_fixture_count=dropped_count,
            removed_type_names=removed_type_names,
            orphan_gdtf_names=orphan_names,
            stripped_tag_counts=dict(stripped_counts),
        ),
    )
    return EnrichResult(data=zip_buf.getvalue(), report=report)
