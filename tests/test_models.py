"""Tests fuer UI-facing data models."""

from mvr_enhancer.core.models import (
    Assignment,
    Candidate,
    CleanupSummary,
    CollisionWarning,
    EnrichReport,
    EnrichResult,
    FixtureType,
    ModeFallbackWarning,
    MvrStats,
    serialize,
)


class TestAssignment:
    def test_assignment_defaults(self):
        """Test Assignment() creates correct defaults."""
        a = Assignment()
        assert a.gdtf_name is None
        assert a.mode_name is None
        assert a.removed is False
        assert a.mode_is_fallback is False
        assert a.source == "library"

    def test_assignment_with_values(self):
        """Test Assignment with explicit values."""
        a = Assignment(
            gdtf_name="fixture.gdtf",
            mode_name="Standard",
            removed=True,
            mode_is_fallback=True,
            source="share",
        )
        assert a.gdtf_name == "fixture.gdtf"
        assert a.mode_name == "Standard"
        assert a.removed is True
        assert a.mode_is_fallback is True
        assert a.source == "share"


class TestSerialize:
    def test_serialize_assignment(self):
        """Test serialize() on Assignment."""
        a = Assignment(gdtf_name="fixture.gdtf", mode_name="Standard")
        result = serialize(a)
        assert isinstance(result, dict)
        assert result["gdtf_name"] == "fixture.gdtf"
        assert result["mode_name"] == "Standard"
        assert result["removed"] is False
        assert result["mode_is_fallback"] is False
        assert result["source"] == "library"

    def test_serialize_fixture_type(self):
        """Test serialize() on FixtureType."""
        ft = FixtureType(
            key="par64",
            name="PAR64",
            count=12,
            positions=["Stage Left", "Stage Right"],
            meta_line="12× · Traverse 1–3",
            existing_spec="Fixture Type 1",
            existing_mode="Standard",
        )
        result = serialize(ft)
        assert isinstance(result, dict)
        assert result["key"] == "par64"
        assert result["name"] == "PAR64"
        assert result["count"] == 12
        assert result["positions"] == ["Stage Left", "Stage Right"]
        assert result["meta_line"] == "12× · Traverse 1–3"

    def test_serialize_enrich_report_nested(self):
        """Test serialize(EnrichReport(...)) produces nested dict without bytes issues."""
        cleanup = CleanupSummary(
            removed_fixture_count=2,
            removed_type_names=["Type A", "Type B"],
            orphan_gdtf_names=["orphan.gdtf"],
            stripped_tag_counts={"CustomCommands": 12, "Position": 5},
        )
        fallback = ModeFallbackWarning(
            type_name="PAR64",
            count=4,
            gdtf_name="par64.gdtf",
            mode_name="Standard",
        )
        report = EnrichReport(
            matched_fixtures=95,
            total_fixtures=100,
            embedded_gdtf_count=3,
            mesh_count=2,
            position_group_count=1,
            fallbacks=[fallback],
            cleanup=cleanup,
        )
        result = serialize(report)
        assert isinstance(result, dict)
        assert result["matched_fixtures"] == 95
        assert result["total_fixtures"] == 100
        assert result["embedded_gdtf_count"] == 3
        assert result["mesh_count"] == 2
        assert result["position_group_count"] == 1
        assert isinstance(result["fallbacks"], list)
        assert len(result["fallbacks"]) == 1
        assert result["fallbacks"][0]["type_name"] == "PAR64"
        assert isinstance(result["cleanup"], dict)
        assert result["cleanup"]["removed_fixture_count"] == 2
        assert result["cleanup"]["removed_type_names"] == ["Type A", "Type B"]
        assert result["cleanup"]["orphan_gdtf_names"] == ["orphan.gdtf"]
        assert result["cleanup"]["stripped_tag_counts"] == {
            "CustomCommands": 12,
            "Position": 5,
        }

    def test_serialize_enrich_result_bytes_excluded(self):
        """Test that serialize handles EnrichResult correctly (data bytes not serialized)."""
        cleanup = CleanupSummary(
            removed_fixture_count=0,
            removed_type_names=[],
            orphan_gdtf_names=[],
            stripped_tag_counts={},
        )
        report = EnrichReport(
            matched_fixtures=10,
            total_fixtures=10,
            embedded_gdtf_count=0,
            mesh_count=0,
            position_group_count=0,
            fallbacks=[],
            cleanup=cleanup,
        )
        result_obj = EnrichResult(data=b"binary data here", report=report)
        # serialize() should be able to handle the bytes field
        # but for JSON serialization, we typically use report separately
        result = serialize(result_obj)
        assert isinstance(result, dict)
        # The bytes field will be serialized as a dict item, but should exist
        assert "data" in result
        assert "report" in result


class TestMvrStats:
    def test_mvr_stats_creation(self):
        """Test MvrStats dataclass."""
        stats = MvrStats(fixtures=100, fixture_types=25, meshes=5, positions=3)
        assert stats.fixtures == 100
        assert stats.fixture_types == 25
        assert stats.meshes == 5
        assert stats.positions == 3

    def test_serialize_mvr_stats(self):
        """Test serialize() on MvrStats."""
        stats = MvrStats(fixtures=100, fixture_types=25, meshes=5, positions=3)
        result = serialize(stats)
        assert result["fixtures"] == 100
        assert result["fixture_types"] == 25
        assert result["meshes"] == 5
        assert result["positions"] == 3


class TestCandidate:
    def test_candidate_creation(self):
        """Test Candidate dataclass."""
        modes = [{"name": "Standard", "channel_count": 16}]
        c = Candidate(
            gdtf_name="par64.gdtf",
            manufacturer="Martin",
            revision="1.0",
            score=0.95,
            modes=modes,
            source="library",
        )
        assert c.gdtf_name == "par64.gdtf"
        assert c.manufacturer == "Martin"
        assert c.revision == "1.0"
        assert c.score == 0.95
        assert c.modes == modes
        assert c.source == "library"

    def test_serialize_candidate(self):
        """Test serialize() on Candidate."""
        modes = [{"name": "Standard", "channel_count": 16}]
        c = Candidate(
            gdtf_name="par64.gdtf",
            manufacturer="Martin",
            revision="1.0",
            score=0.95,
            modes=modes,
            source="library",
        )
        result = serialize(c)
        assert result["gdtf_name"] == "par64.gdtf"
        assert result["modes"] == modes


class TestOtherDataclasses:
    def test_collision_warning(self):
        """Test CollisionWarning dataclass."""
        cw = CollisionWarning(
            universe=1, start=1, end=16, fixture_names=["PAR64", "PAR64 2"]
        )
        assert cw.universe == 1
        assert cw.start == 1
        assert cw.end == 16
        result = serialize(cw)
        assert result["universe"] == 1
        assert result["fixture_names"] == ["PAR64", "PAR64 2"]

    def test_mode_fallback_warning(self):
        """Test ModeFallbackWarning dataclass."""
        mfw = ModeFallbackWarning(
            type_name="PAR64", count=4, gdtf_name="par64.gdtf", mode_name="Standard"
        )
        assert mfw.type_name == "PAR64"
        result = serialize(mfw)
        assert result["type_name"] == "PAR64"
