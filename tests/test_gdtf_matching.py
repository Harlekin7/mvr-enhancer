"""Tests fuer GDTF Score-Matching."""

from mvr_enhancer.core.gdtf import _normalize, score_match


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("GLP X5") == "glp x5"

    def test_replaces_separators(self):
        result = _normalize("Martin-MAC_Viper@Profile")
        assert "-" not in result
        assert "_" not in result
        assert "@" not in result


class TestScoreMatch:
    def test_exact_match_returns_one(self):
        assert score_match("GLP X5", "GLP X5") == 1.0

    def test_case_insensitive_match(self):
        assert score_match("glp x5", "GLP X5") == 1.0

    def test_no_match_returns_zero(self):
        assert score_match("GLP X5", "Robe Spiider") == 0.0

    def test_empty_strings_return_zero(self):
        assert score_match("", "") == 0.0
        assert score_match("GLP X5", "") == 0.0
        assert score_match("", "GLP X5") == 0.0

    def test_partial_match_above_threshold(self):
        score = score_match("MAC Viper", "Martin MAC Viper Profile")
        assert 0.6 <= score <= 1.0

    def test_manufacturer_helps_matching(self):
        # Test dass Hersteller-Name bei Combined-Matching hilft
        score_without_mfg = score_match("Viper", "MAC Viper Profile")
        score_with_mfg = score_match("Viper", "MAC Viper Profile", "Martin")
        assert score_with_mfg > score_without_mfg

    def test_unrelated_fixtures_score_below_threshold(self):
        score = score_match("ETC Source Four", "Robe MegaPointe")
        assert score < 0.6
