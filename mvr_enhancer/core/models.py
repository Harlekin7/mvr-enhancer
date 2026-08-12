"""UI-facing data models for MVR Enhancer."""

from dataclasses import asdict, dataclass


@dataclass
class FixtureType:
    """Represents a fixture type in the MVR."""

    key: str  # normalisierter Name (core.gdtf._normalize)
    name: str  # Anzeigename (häufigster Original-Name)
    count: int
    positions: list[str]
    meta_line: str  # z. B. "24× · Traverse 1–3" bzw. "24× · ohne Position"
    existing_spec: str  # GDTFSpec aus dem MVR, "" wenn leer
    existing_mode: str


@dataclass
class Candidate:
    """Represents a GDTF fixture candidate from matching."""

    gdtf_name: str  # Dateiname/Fixture-Name in Bibliothek
    manufacturer: str
    revision: str
    score: float
    modes: list[dict]  # [{"name": str, "channel_count": int}]
    source: str  # "library" | "share" | "vectorwatch"


@dataclass
class Assignment:
    """Represents the assignment of a fixture type to a GDTF fixture."""

    gdtf_name: str | None = None  # None = offen; "" nie verwenden
    mode_name: str | None = None
    removed: bool = False  # True = Typ wird aus Export entfernt
    mode_is_fallback: bool = False
    source: str = "library"


@dataclass
class MvrStats:
    """Statistics about the MVR file."""

    fixtures: int
    fixture_types: int
    meshes: int
    positions: int


@dataclass
class ModeFallbackWarning:
    """Warning about a fixture type using a fallback mode."""

    type_name: str
    count: int
    gdtf_name: str
    mode_name: str


@dataclass
class CollisionWarning:
    """Warning about a DMX universe collision."""

    universe: int
    start: int
    end: int
    fixture_names: list[str]


@dataclass
class CleanupSummary:
    """Summary of cleanup operations."""

    removed_fixture_count: int
    removed_type_names: list[str]
    orphan_gdtf_names: list[str]
    stripped_tag_counts: dict[str, int]  # {"CustomCommands": 12, "Position": 12}


@dataclass
class EnrichReport:
    """Report from enriching an MVR file."""

    matched_fixtures: int
    total_fixtures: int
    embedded_gdtf_count: int
    mesh_count: int
    position_group_count: int
    fallbacks: list[ModeFallbackWarning]
    cleanup: CleanupSummary


@dataclass
class EnrichResult:
    """Result of enriching an MVR file."""

    data: bytes
    report: EnrichReport


def serialize(obj) -> dict:
    """Serialize a dataclass to a dict using dataclasses.asdict.

    Args:
        obj: A dataclass instance.

    Returns:
        A dictionary representation of the dataclass.
    """
    return asdict(obj)
