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
from mvr_enhancer.core.gdtf import (
    GdtfFixture,
    GdtfMode,
    _normalize,
    find_gdtf_file,
    find_matching_gdtf,
)
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


def _resolve_mode_name(vw_mode: str, modes: list[GdtfMode]) -> tuple[str, bool]:
    """Bestimmt den GDTF-Modus per Substring-Abgleich, sonst ``modes[0]``.

    Gibt ``(mode_name, confirmed)`` zurueck: ``confirmed=True`` nur, wenn ein
    tatsaechlicher Substring-Treffer gegen den urspruenglichen MVR-Modus-Text
    gefunden wurde — der reine ``modes[0]``-Notnagel gilt nicht als bestaetigt
    und muss im Report als Fallback auftauchen.
    """
    vw_mode_lower = (vw_mode or "").lower()
    if vw_mode_lower:
        for mode in modes:
            mode_lower = mode.name.lower()
            if vw_mode_lower in mode_lower or mode_lower in vw_mode_lower:
                return mode.name, True
    return modes[0].name, False


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

    # AUXData kommt laut MVR-Spec-Reihenfolge vor Layers innerhalb von Scene.
    if scene.aux_data is not None:
        scene_el.append(scene.aux_data)

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

    return root, position_group_count


def compute_gdtf_references(
    scene: MvrScene,
    assignments: dict[str, Assignment],
    gdtf_library_dir: str,
    gdtf_library: dict[str, GdtfFixture],
) -> set[str]:
    """Berechnet, ohne den Export-Baum zu bauen, welche GDTFSpec-Referenzen
    ein ``enrich_mvr``-Lauf mit denselben Parametern im exportierten Baum
    hinterlassen wuerde.

    Deckt zwei Faelle ab, die sich rein aus ``assignments`` nicht ablesen
    lassen:

    - Eine zugeordnete Fixture, deren ``Assignment.gdtf_name`` sich zu keiner
      Bibliotheksdatei aufloesen laesst: ``_update_fixture_element`` laesst
      deren *urspruengliches* ``GDTFSpec`` in diesem Fall unangetastet — das
      referenzierte eingebettete GDTF ueberlebt also trotz fehlgeschlagener
      Aufloesung.
    - In opaken Nicht-Fixture-Elementen verschachtelte Fixtures (z. B. ein
      ``<Fixture>`` innerhalb ``<SceneObject>``): ``mvr_reader`` erfasst sie
      nicht als ``MvrFixture``, sie werden aber unveraendert in die "3D"-
      Gruppe uebernommen und referenzieren ihr GDTF weiterhin gueltig.

    Wird sowohl von ``enrich_mvr`` selbst (Orphan-Bereinigung) als auch von
    der API-Export-Vorschau (``api.Api.prepare_export`` -> ``cleanup_preview``)
    genutzt, damit beide nicht auseinanderlaufen koennen.
    """
    fixtures_by_type: dict[str, list[MvrFixture]] = {}
    for fixture in scene.fixtures:
        key = _normalize(fixture.name)
        assignment = assignments.get(key)
        if assignment is None or not assignment.gdtf_name or assignment.removed:
            continue
        fixtures_by_type.setdefault(key, []).append(fixture)

    reference_keys: set[str] = set()

    for key, fixtures_of_type in fixtures_by_type.items():
        assignment = assignments[key]
        gdtf_name = assignment.gdtf_name or ""

        exact_match = gdtf_library.get(gdtf_name) if gdtf_name else None
        matched = exact_match
        if matched is None and gdtf_name:
            matched = find_matching_gdtf(gdtf_name, gdtf_library, {})

        abs_path = find_gdtf_file(
            gdtf_name, gdtf_library_dir, gdtf_library, {}, matched=matched,
        )
        if abs_path and os.path.isfile(abs_path):
            zip_name = _clean_gdtf_name(os.path.basename(abs_path))
            reference_keys |= _gdtf_ref_keys(zip_name)
        else:
            # Aufloesung fehlgeschlagen: _update_fixture_element laesst das
            # urspruengliche GDTFSpec in diesem Fall unangetastet.
            for fixture in fixtures_of_type:
                if fixture.gdtf_spec:
                    reference_keys |= _gdtf_ref_keys(fixture.gdtf_spec)

    for element in scene.non_fixture_elements:
        for gdtf_el in element.iter("GDTFSpec"):
            if gdtf_el.text:
                reference_keys |= _gdtf_ref_keys(gdtf_el.text)

    return reference_keys


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
        # (gdtf_name is None or "" — e.g. a still-open UI row), or it was
        # explicitly marked removed (e.g. a plugbox/distro with no GDTF).
        if assignment is None or not assignment.gdtf_name or assignment.removed:
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
        fixture_type = type_by_key.get(key)
        gdtf_name = assignment.gdtf_name or ""

        # Exact library-key match first; if the assignment's gdtf_name isn't
        # an exact key (e.g. a display name that doesn't match the library's
        # dict key verbatim), fall back to the same fuzzy scoring find_gdtf_file
        # would otherwise use internally — but resolve it *here* too, so the
        # GdtfFixture used for mode resolution is guaranteed to be the same
        # one whose file actually gets embedded (previously: on an exact-key
        # miss, `matched` stayed None even though find_gdtf_file(matched=None)
        # went on to fuzzy-resolve and embed a *different* file, leaving the
        # mode resolution blind to that file's real modes and the original,
        # possibly stale, MVR GDTFMode text untouched with no warning).
        exact_match = gdtf_library.get(gdtf_name) if gdtf_name else None
        matched = exact_match
        if matched is None and gdtf_name:
            matched = find_matching_gdtf(gdtf_name, gdtf_library, {})
        # An explicit user assignment silently resolving to a *different*
        # GDTF than the name it named must not pass unreported.
        gdtf_substituted = bool(gdtf_name) and exact_match is None and matched is not None

        zip_name = ""
        abs_path = find_gdtf_file(
            gdtf_name, gdtf_library_dir, gdtf_library, {}, matched=matched,
        )
        if abs_path and os.path.isfile(abs_path):
            zip_name = _clean_gdtf_name(os.path.basename(abs_path))
            gdtf_paths[zip_name] = abs_path
        type_gdtf_filename[key] = zip_name

        needs_warning = gdtf_substituted
        if assignment.mode_name:
            mode_name = assignment.mode_name
        elif matched is not None and matched.modes:
            existing_mode = fixture_type.existing_mode if fixture_type else ""
            mode_name, confirmed = _resolve_mode_name(existing_mode, matched.modes)
            if not confirmed:
                needs_warning = True
        else:
            # Mode resolution failed entirely (no matched GDTF, or a matched
            # GDTF with no modes at all) — always report this.
            mode_name = ""
            needs_warning = True
        type_mode_name[key] = mode_name

        if needs_warning:
            fallbacks.append(
                ModeFallbackWarning(
                    type_name=fixture_type.name if fixture_type else fixtures_of_type[0].name,
                    count=len(fixtures_of_type),
                    gdtf_name=matched.name if matched is not None else gdtf_name,
                    mode_name=mode_name,
                )
            )

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

    # 4b. Nicht-standardkonforme Elemente entfernen — ueber ALLE <Fixture>-
    #     Elemente im finalen Baum (``root.iter("Fixture")``), nicht nur
    #     ``kept_fixtures``: Fixtures, die in einem opaken Nicht-Fixture-
    #     Element verschachtelt sind (z. B. ein <Fixture> innerhalb eines
    #     <SceneObject>/<Truss>), landen unveraendert in der "3D"-Gruppe
    #     (``mvr_reader`` rekursiert nur in GroupObject, nicht in andere Tags)
    #     und muessten sonst poison-Elemente behalten. Bewusst NICHT ueber
    #     ``root.iter()`` (alle Elemente): ``AUXData`` hat eigene ``Position``-
    #     Kinder (Positions-*Definitionen*, keine Fixture-Referenzen) mit
    #     demselben Tag-Namen — die duerfen nicht mitgestrippt werden.
    stripped_counts: Counter = Counter()
    for fixture_el in root.iter("Fixture"):
        _strip_nonstandard_elements(fixture_el, stripped_counts)

    # 4c. In-Place-Dekodierung verbliebener URL-kodierter GDTFSpec-Werte im
    #     finalen Baum (fuer die tatsaechliche Export-Ausgabe).
    for gdtf_el in root.iter("GDTFSpec"):
        if gdtf_el.text and "%" in gdtf_el.text:
            gdtf_el.text = _clean_gdtf_name(gdtf_el.text)

    # Referenz-Set ueber die gemeinsame Hilfsfunktion (siehe deren Docstring):
    # dieselbe Logik treibt auch api.Api.prepare_export()s Export-Vorschau,
    # damit beide Berechnungen nicht auseinanderlaufen koennen.
    reference_keys = compute_gdtf_references(scene, assignments, gdtf_library_dir, gdtf_library)

    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)
    xml_buf = io.BytesIO()
    tree.write(xml_buf, encoding="UTF-8", xml_declaration=True)
    xml_data = xml_buf.getvalue()

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
