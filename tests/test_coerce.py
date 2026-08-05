"""Tests fuer zentrale Coerce-Helper (Audit Q6/Q7)."""

import pytest

from mvr_enhancer.core._coerce import safe_bool, safe_float, safe_int, safe_str


class TestSafeStr:
    def test_normal_string(self):
        assert safe_str("hello") == "hello"

    def test_none_returns_default(self):
        assert safe_str(None) == ""
        assert safe_str(None, default="N/A") == "N/A"

    def test_int_to_str(self):
        assert safe_str(42) == "42"

    def test_strip_whitespace(self):
        assert safe_str("  hello  ") == "hello"


class TestSafeInt:
    def test_int_passes(self):
        assert safe_int(42) == 42

    def test_str_to_int(self):
        assert safe_int("42") == 42

    def test_invalid_returns_default(self):
        assert safe_int("abc") == 0
        assert safe_int("abc", default=99) == 99

    def test_none_returns_default(self):
        assert safe_int(None) == 0

    def test_float_string_to_int(self):
        assert safe_int("42.7") == 42


class TestSafeFloat:
    def test_float_passes(self):
        assert safe_float(3.14) == 3.14

    def test_str_to_float(self):
        assert safe_float("3.14") == 3.14

    def test_comma_decimal(self):
        """Deutsche Dezimaltrennung wird akzeptiert."""
        assert safe_float("3,14") == 3.14

    def test_invalid_returns_default(self):
        assert safe_float("abc") == 0.0
        assert safe_float("abc", default=1.0) == 1.0


class TestSafeBool:
    @pytest.mark.parametrize("truthy", [True, 1, "true", "True", "yes", "1"])
    def test_truthy_values(self, truthy):
        assert safe_bool(truthy) is True

    @pytest.mark.parametrize("falsy", [False, 0, "false", "False", "no", "0", None, ""])
    def test_falsy_values(self, falsy):
        assert safe_bool(falsy) is False
