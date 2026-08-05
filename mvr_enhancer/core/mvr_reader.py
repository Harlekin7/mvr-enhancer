"""MVR-Reader — Liest MVR-Dateien (DIN SPEC 15801) und parst die Szene.

Eine MVR-Datei ist ein ZIP-Archiv mit GeneralSceneDescription.xml
und eingebetteten Dateien (.gdtf, .3ds, etc.).
"""

import logging
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field

import defusedxml.ElementTree as SafeET

from mvr_enhancer.core.constants import (
    MAX_MVR_EMBEDDED_FILE_COUNT as _MAX_EMBEDDED_FILE_COUNT,
)
from mvr_enhancer.core.constants import (
    MAX_MVR_EMBEDDED_FILE_SIZE as _MAX_EMBEDDED_FILE_SIZE,
)
from mvr_enhancer.core.constants import (
    MAX_MVR_TOTAL_EXTRACTED as _MAX_TOTAL_EXTRACTED_SIZE,
)
from mvr_enhancer.core.constants import (
    MAX_MVR_XML_SIZE as _MAX_XML_SIZE,
)

log = logging.getLogger(__name__)


def _safe_parse_xml(xml_data: bytes) -> ET.Element:
    """Parst XML mit Entity-Expansion-Schutz und Groessenlimit.

    Verwendet defusedxml zum Schutz vor Billion-Laughs und
    aehnlichen XML-Entity-Expansion-Angriffen.
    """
    if len(xml_data) > _MAX_XML_SIZE:
        raise ValueError(
            f"XML data exceeds size limit ({len(xml_data)} > {_MAX_XML_SIZE})"
        )
    return SafeET.fromstring(xml_data)


# Element-Tags die als Fixture gelten
_FIXTURE_TAG = "Fixture"

# Maximale Anzahl URL-Dekodier-Runden fuer ZIP-Eintragsnamen (siehe
# ``_fully_unquote``) — mehr als eine Handvoll Runden ist ausschliesslich
# ein Angriffsmuster, nicht ein echter Dateiname.
_MAX_UNQUOTE_ROUNDS = 8


def _fully_unquote(name: str) -> str:
    """URL-dekodiert ``name`` wiederholt, bis sich nichts mehr aendert.

    Notwendig, weil die Export-Seite (``enricher._clean_gdtf_name``) den
    Eintragsnamen dekodiert, bevor sie ihn erneut ins ZIP schreibt: ein roher
    Eintrag ``%2E%2E%2F..%2Fevil.gdtf`` sieht als Klartext harmlos aus, wird
    beim Export aber zu einem echten ``../../evil.gdtf``. Die Traversal-
    Pruefung muss deshalb auf der voll dekodierten Form arbeiten — und zwar
    idempotent, damit auch mehrfach kodierte Namen (``%252E%252E%252F``)
    erfasst werden.
    """
    current = name
    for _ in range(_MAX_UNQUOTE_ROUNDS):
        decoded = urllib.parse.unquote(current)
        if decoded == current:
            return current
        current = decoded
    return current


def _is_unsafe_entry_name(name: str) -> bool:
    """True, wenn ein ZIP-Eintragsname aus dem Archiv-Root ausbrechen kann.

    Prueft die voll dekodierte Form (siehe ``_fully_unquote``) auf absolute
    Pfade, Windows-Laufwerksbuchstaben und ``..``-Segmente.
    """
    normalized = _fully_unquote(name).replace("\\", "/")
    if not normalized:
        return True
    if normalized.startswith("/"):
        return True
    if len(normalized) > 1 and normalized[1] == ":":
        return True
    return ".." in normalized.split("/")


@dataclass
class MvrFixture:
    """Ein geparster Fixture-Eintrag aus dem MVR."""

    element: ET.Element
    uuid: str = ""
    name: str = ""
    gdtf_spec: str = ""
    gdtf_mode: str = ""
    dmx_address: int = 0
    matrix: str = ""


@dataclass
class MvrScene:
    """Komplette geparste MVR-Szene."""

    xml_root: ET.Element | None = None
    fixtures: list[MvrFixture] = field(default_factory=list)
    non_fixture_elements: list[ET.Element] = field(default_factory=list)
    embedded_files: dict[str, bytes] = field(default_factory=dict)
    user_data: ET.Element | None = None
    aux_data: ET.Element | None = None


def _parse_fixture(element: ET.Element) -> MvrFixture:
    """Parst ein Fixture-XML-Element zu MvrFixture."""
    uuid_val = element.get("uuid", "")
    name_val = element.get("name", "")

    gdtf_spec_el = element.find("GDTFSpec")
    gdtf_spec = gdtf_spec_el.text or "" if gdtf_spec_el is not None else ""

    gdtf_mode_el = element.find("GDTFMode")
    gdtf_mode = gdtf_mode_el.text or "" if gdtf_mode_el is not None else ""

    matrix_el = element.find("Matrix")
    matrix_text = matrix_el.text or "" if matrix_el is not None else ""

    dmx_address = 0
    addresses_el = element.find("Addresses")
    if addresses_el is not None:
        addr_el = addresses_el.find("Address")
        if addr_el is not None and addr_el.text:
            try:
                dmx_address = int(addr_el.text)
            except ValueError:
                pass

    return MvrFixture(
        element=element,
        uuid=uuid_val,
        name=name_val,
        gdtf_spec=gdtf_spec,
        gdtf_mode=gdtf_mode,
        dmx_address=dmx_address,
        matrix=matrix_text,
    )


def _collect_elements(parent: ET.Element,
                      fixtures: list[MvrFixture],
                      non_fixtures: list[ET.Element]) -> None:
    """Traversiert rekursiv den XML-Baum und sammelt Fixtures und Nicht-Fixtures.

    Geht durch ChildList-Elemente in Layers, Layer, GroupObject, etc.
    """
    for child_list in parent.findall("ChildList"):
        for element in list(child_list):
            if element.tag == _FIXTURE_TAG:
                fixtures.append(_parse_fixture(element))
            elif element.tag == "GroupObject":
                # GroupObject rekursiv durchsuchen — Fixtures extrahieren,
                # Nicht-Fixtures behalten
                group_fixtures: list[MvrFixture] = []
                group_non_fixtures: list[ET.Element] = []
                _collect_elements(element, group_fixtures, group_non_fixtures)
                fixtures.extend(group_fixtures)
                non_fixtures.extend(group_non_fixtures)
            else:
                # Truss, SceneObject, Support, FocusPoint, etc.
                non_fixtures.append(element)

    # Auch direkte Kinder von Layer durchsuchen (ohne ChildList-Wrapper)
    if parent.tag == "Layer":
        child_list = parent.find("ChildList")
        if child_list is None:
            # Manche MVR-Dateien haben Elemente direkt unter Layer
            for element in list(parent):
                if element.tag in ("Matrix", "ChildList"):
                    continue
                if element.tag == _FIXTURE_TAG:
                    fixtures.append(_parse_fixture(element))
                elif element.tag == "GroupObject":
                    group_fixtures_: list[MvrFixture] = []
                    group_non_fixtures_: list[ET.Element] = []
                    _collect_elements(element, group_fixtures_, group_non_fixtures_)
                    fixtures.extend(group_fixtures_)
                    non_fixtures.extend(group_non_fixtures_)
                else:
                    non_fixtures.append(element)


def read_mvr(path: str) -> MvrScene:
    """Liest ein MVR-Archiv und parst die GeneralSceneDescription.

    Args:
        path: Pfad zur .mvr Datei.

    Returns:
        MvrScene mit geparsten Fixtures, Nicht-Fixture-Elementen und
        eingebetteten Dateien.
    """
    scene = MvrScene()

    try:
        zf = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile as e:
        log.error("MVR-Datei ist keine gueltige ZIP-Datei: %s — %s", path, e)
        return scene
    except OSError as e:
        log.error("MVR-Datei konnte nicht gelesen werden: %s — %s", path, e)
        return scene

    with zf:
        # Alle eingebetteten Dateien lesen (mit ZIP-Bomb-Schutz)
        total_extracted = 0
        file_count = 0
        for name in zf.namelist():
            if name == "GeneralSceneDescription.xml":
                continue
            if _is_unsafe_entry_name(name):
                log.warning(
                    "Eingebetteter ZIP-Eintrag mit Pfad-Traversal "
                    "uebersprungen: %s",
                    name,
                )
                continue
            file_count += 1
            if file_count > _MAX_EMBEDDED_FILE_COUNT:
                log.warning(
                    "MVR-Archiv enthaelt zu viele Dateien (>%d), "
                    "ueberspringe restliche: %s",
                    _MAX_EMBEDDED_FILE_COUNT, path,
                )
                break
            info = zf.getinfo(name)
            if info.file_size > _MAX_EMBEDDED_FILE_SIZE:
                log.warning(
                    "Eingebettete Datei zu gross, uebersprungen: %s "
                    "(%d bytes > %d bytes)",
                    name, info.file_size, _MAX_EMBEDDED_FILE_SIZE,
                )
                continue
            if total_extracted + info.file_size > _MAX_TOTAL_EXTRACTED_SIZE:
                log.warning(
                    "MVR-Archiv Gesamt-Extraktionslimit erreicht "
                    "(%d bytes), breche ab: %s",
                    _MAX_TOTAL_EXTRACTED_SIZE, path,
                )
                break
            data = zf.read(name)
            total_extracted += len(data)
            scene.embedded_files[name] = data

        # XML parsen
        xml_name = "GeneralSceneDescription.xml"
        if xml_name not in zf.namelist():
            log.error("MVR enthaelt keine %s: %s", xml_name, path)
            return scene

        xml_data = zf.read(xml_name)
        scene.xml_root = _safe_parse_xml(xml_data)

    # UserData und AUXData preservieren
    scene.user_data = scene.xml_root.find("UserData")

    # Szene traversieren
    scene_el = scene.xml_root.find("Scene")
    if scene_el is None:
        log.warning("Kein <Scene>-Element in MVR: %s", path)
        return scene

    scene.aux_data = scene_el.find("AUXData")

    layers_el = scene_el.find("Layers")
    if layers_el is None:
        log.warning("Kein <Layers>-Element in MVR: %s", path)
        return scene

    for layer in layers_el.findall("Layer"):
        _collect_elements(layer, scene.fixtures, scene.non_fixture_elements)

    log.info("MVR gelesen: %s (%d Fixtures, %d Nicht-Fixture-Elemente, %d Dateien)",
             path, len(scene.fixtures), len(scene.non_fixture_elements),
             len(scene.embedded_files))
    return scene
