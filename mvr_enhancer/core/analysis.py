"""MVR-Analyse: Typ-Aggregation, Positionen, Statistiken, Adress-Kollisionen.

Baut auf den von ``mvr_reader.read_mvr`` gelieferten ``MvrScene``/``MvrFixture``-
Objekten auf, ohne den Reader selbst zu veraendern. Positions- und Layer-
Zugehoerigkeit werden hier direkt aus ``scene.xml_root`` bzw. ``scene.aux_data``
rekonstruiert.
"""

import os
from collections import Counter, defaultdict

from mvr_enhancer.core.gdtf import _normalize
from mvr_enhancer.core.models import Assignment, CollisionWarning, FixtureType, MvrStats
from mvr_enhancer.core.mvr_reader import MvrFixture, MvrScene

# Datei-Endungen die als 3D-Mesh gelten (case-insensitiv geprueft).
_MESH_EXTENSIONS = {".glb", ".3ds", ".gltf", ".obj", ".fbx"}

_NO_POSITION = "ohne Position"

_DMX_CHANNELS_PER_UNIVERSE = 512


def parse_position_names(scene: MvrScene) -> dict[str, str]:
    """Baut eine UUID→Name-Map aus den ``AUXData/Position``-Definitionen.

    ``AUXData/Position``-Elemente sind laut MVR-Spec direkte Kinder von
    ``AUXData`` und tragen ``uuid``/``name`` als Attribute. Gibt ein leeres
    Dict zurueck, wenn die Szene kein ``AUXData``-Element enthaelt.
    """
    result: dict[str, str] = {}
    if scene.aux_data is None:
        return result

    for position_el in scene.aux_data.findall("Position"):
        uuid = position_el.get("uuid")
        if not uuid:
            continue
        result[uuid] = position_el.get("name", "")

    return result


def _build_layer_map(scene: MvrScene) -> dict[str, str]:
    """Baut eine Fixture-UUID→Layer-Name-Map durch Traversieren von ``xml_root``.

    Layer-Zugehoerigkeit ist in ``MvrFixture`` nicht abgebildet, daher wird
    hier direkt ueber den XML-Baum gegangen: fuer jedes ``Layer``-Element
    (auch verschachtelt in ``GroupObject`` u.ae.) werden alle enthaltenen
    ``Fixture``-UUIDs auf den ``name``-Attributwert des Layers gemappt.
    """
    layer_map: dict[str, str] = {}
    if scene.xml_root is None:
        return layer_map

    for layer_el in scene.xml_root.iter("Layer"):
        layer_name = layer_el.get("name", "")
        for fixture_el in layer_el.iter("Fixture"):
            uuid = fixture_el.get("uuid")
            if uuid:
                layer_map[uuid] = layer_name

    return layer_map


def _resolve_position(
    fixture: MvrFixture,
    position_names: dict[str, str],
    layer_map: dict[str, str],
) -> str:
    """Loest den Positionsnamen einer Fixture-Instanz auf.

    Reihenfolge: ``<Position>``-Kind-UUID → AUXData-Name; Fallback: Name des
    Layers, in dem das Fixture liegt; sonst "ohne Position".
    """
    position_el = fixture.element.find("Position")
    if position_el is not None and position_el.text:
        position_uuid = position_el.text.strip()
        name = position_names.get(position_uuid)
        if name:
            return name

    layer_name = layer_map.get(fixture.uuid)
    if layer_name:
        return layer_name

    return _NO_POSITION


def aggregate_fixture_types(scene: MvrScene) -> list[FixtureType]:
    """Gruppiert Fixtures nach normalisiertem Namen zu ``FixtureType``-Eintraegen."""
    position_names = parse_position_names(scene)
    layer_map = _build_layer_map(scene)

    groups: dict[str, list[MvrFixture]] = {}
    order: list[str] = []
    for fixture in scene.fixtures:
        key = _normalize(fixture.name)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(fixture)

    types: list[FixtureType] = []
    for key in order:
        fixtures = groups[key]

        position_set: set[str] = set()
        for fixture in fixtures:
            position_set.add(_resolve_position(fixture, position_names, layer_map))
        positions = sorted(position_set)

        count = len(fixtures)
        meta_line = f"{count}× · {', '.join(positions[:3])}"
        if len(positions) > 3:
            meta_line += " …"

        name_counts = Counter(f.name for f in fixtures)
        display_name = name_counts.most_common(1)[0][0]

        types.append(
            FixtureType(
                key=key,
                name=display_name,
                count=count,
                positions=positions,
                meta_line=meta_line,
                existing_spec=fixtures[0].gdtf_spec,
                existing_mode=fixtures[0].gdtf_mode,
            )
        )

    return types


def compute_stats(scene: MvrScene, types: list[FixtureType]) -> MvrStats:
    """Berechnet Kennzahlen (Fixture-/Typ-Anzahl, Meshes, Positionen) fuer die Szene."""
    meshes = sum(
        1
        for name in scene.embedded_files
        if os.path.splitext(name)[1].lower() in _MESH_EXTENSIONS
    )

    position_names: set[str] = set()
    for fixture_type in types:
        for position in fixture_type.positions:
            if position != _NO_POSITION:
                position_names.add(position)

    return MvrStats(
        fixtures=len(scene.fixtures),
        fixture_types=len(types),
        meshes=meshes,
        positions=len(position_names),
    )


def detect_address_collisions(
    scene: MvrScene,
    types: list[FixtureType],
    assignments: dict[str, Assignment],
    footprints: dict[str, int],
) -> list[CollisionWarning]:
    """Erkennt ueberlappende DMX-Adressbereiche je Universum.

    Je Fixture-Instanz wird das absolute Intervall ``[addr, addr+footprint-1]``
    gebildet und ueber ``divmod(addr-1, 512)`` einem Universum (1-basiert) mit
    1-basierten Kanalnummern zugeordnet. Entfernte Typen (``removed``) und
    Typen ohne Assignment werden ausgelassen. Pro ueberlappendem Cluster wird
    genau eine ``CollisionWarning`` erzeugt.
    """
    valid_keys = {fixture_type.key for fixture_type in types}

    intervals_by_universe: dict[int, list[tuple[int, int, str]]] = defaultdict(list)

    for fixture in scene.fixtures:
        key = _normalize(fixture.name)
        if key not in valid_keys:
            continue

        assignment = assignments.get(key)
        if assignment is None or assignment.removed:
            continue

        footprint = footprints.get(key)
        if not footprint:
            continue

        universe_index, channel_index = divmod(fixture.dmx_address - 1, _DMX_CHANNELS_PER_UNIVERSE)
        start_channel = channel_index + 1
        end_channel = start_channel + footprint - 1
        universe = universe_index + 1

        intervals_by_universe[universe].append((start_channel, end_channel, fixture.name))

    warnings: list[CollisionWarning] = []
    for universe in sorted(intervals_by_universe):
        intervals = sorted(intervals_by_universe[universe], key=lambda item: item[0])

        cluster: list[tuple[int, int, str]] = []
        cluster_end = None
        for interval in intervals:
            start, end, name = interval
            if cluster and start <= cluster_end:
                cluster.append(interval)
                cluster_end = max(cluster_end, end)
            else:
                if cluster and len(cluster) > 1:
                    warnings.append(_make_collision_warning(universe, cluster))
                cluster = [interval]
                cluster_end = end
        if cluster and len(cluster) > 1:
            warnings.append(_make_collision_warning(universe, cluster))

    return warnings


def _make_collision_warning(
    universe: int, cluster: list[tuple[int, int, str]]
) -> CollisionWarning:
    """Baut eine ``CollisionWarning`` aus einem Cluster ueberlappender Intervalle."""
    start = min(item[0] for item in cluster)
    end = max(item[1] for item in cluster)
    fixture_names = [item[2] for item in cluster]
    return CollisionWarning(universe=universe, start=start, end=end, fixture_names=fixture_names)
