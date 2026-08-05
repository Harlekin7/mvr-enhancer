"""Tests fuer DPAPI-Passwortverschluesselung (``mvr_enhancer/winsec.py``)."""

import sys

import pytest

from mvr_enhancer import winsec


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI ist Windows-spezifisch")
def test_encrypt_decrypt_roundtrip():
    encrypted = winsec.encrypt_password("s3cr3t!")

    assert encrypted != "s3cr3t!"
    assert encrypted.startswith("dpapi:")
    assert winsec.decrypt_password(encrypted) == "s3cr3t!"


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI ist Windows-spezifisch")
def test_empty_string_roundtrip():
    assert winsec.encrypt_password("") == ""
    assert winsec.decrypt_password("") == ""


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI ist Windows-spezifisch")
def test_decrypt_rejects_plaintext_without_prefix():
    assert winsec.decrypt_password("plaintext-password") == ""


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI ist Windows-spezifisch")
def test_decrypt_handles_garbage_after_prefix():
    assert winsec.decrypt_password("dpapi:not-valid-base64-!!!") == ""


def test_non_windows_raises_value_error(monkeypatch):
    monkeypatch.setattr(winsec.sys, "platform", "linux")

    with pytest.raises(ValueError):
        winsec.encrypt_password("x")
    with pytest.raises(ValueError):
        winsec.decrypt_password("dpapi:abc")


def test_non_windows_empty_string_roundtrip_still_works(monkeypatch):
    monkeypatch.setattr(winsec.sys, "platform", "linux")

    assert winsec.encrypt_password("") == ""
    assert winsec.decrypt_password("") == ""
