"""TASK-257 — credential-envelope classification + orphan-alert message logic.

Pure-logic tests only: the DB-bound scans (envelope_classification, the CLI)
are covered by the compose integration smokes; here we pin the classifier's
three-way split and the gate's rewrap-able arithmetic, which decide whether
boot strands or continues.
"""
import base64
import hashlib

from cryptography.fernet import Fernet

from core.secrets import _classify_values, _decrypts_under, _fernet_from_source

_PRIMARY = "primary_test_key_source"
_FALLBACK = "fallback_test_key_source"

_PRIMARY_FERNET = _fernet_from_source(_PRIMARY)
_CHAIN_FERNETS = [_PRIMARY_FERNET, _fernet_from_source(_FALLBACK)]


def _encrypt(value: str, fernet: Fernet) -> str:
    return f"enc:v1:{fernet.encrypt(value.encode('utf-8')).decode('ascii')}"


def test_classify_values_splits_current_rewrap_able_orphaned():
    values = [
        _encrypt("under-primary", _PRIMARY_FERNET),                     # current
        _encrypt("under-fallback", _fernet_from_source(_FALLBACK)),     # rewrap-able
        "enc:v1:gAAAA_bogus_ciphertext_never_decryptable",              # orphaned
    ]
    counts = _classify_values(values, _CHAIN_FERNETS, _PRIMARY_FERNET)
    assert counts == {"current": 1, "rewrap_able": 1, "orphaned": 1}


def test_classify_values_empty():
    assert _classify_values([], _CHAIN_FERNETS, _PRIMARY_FERNET) == {
        "current": 0, "rewrap_able": 0, "orphaned": 0,
    }


def test_rewrap_able_is_relative_to_the_primary():
    # The same ciphertext flips current → rewrap-able when the primary moves
    # to the dedicated key: this is the invariant the startup gate's
    # must_rewrap arithmetic relies on.
    value = _encrypt("same-plaintext", _fernet_from_source(_FALLBACK))
    assert _decrypts_under(value, _fernet_from_source(_FALLBACK))
    assert not _decrypts_under(value, _fernet_from_source(_PRIMARY))
    assert _classify_values([value], _CHAIN_FERNETS, _PRIMARY_FERNET)["rewrap_able"] == 1
    assert _classify_values(
        [value], _CHAIN_FERNETS, _fernet_from_source(_FALLBACK)
    )["current"] == 1


def test_fernet_from_source_matches_the_deployed_key_shape():
    # The chain is sha256(source) → urlsafe-b64 → Fernet. Pin it: a key built
    # this way must decrypt what an equally-built key encrypted.
    source = "x" * 44
    fernet = _fernet_from_source(source)
    token = fernet.encrypt(b"roundtrip")
    assert Fernet(base64.urlsafe_b64encode(hashlib.sha256(source.encode()).digest())).decrypt(token) == b"roundtrip"
