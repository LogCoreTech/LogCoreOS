"""Tests for infisical_loader.py's at-rest encryption of the secrets cache and
token file. No brain fixture here — infisical_loader reads BRAIN_PATH directly
from os.environ (not settings.brain_path), so tests set the env var directly."""

import json

import pytest
from cryptography.fernet import Fernet

import services.infisical_loader as il


@pytest.fixture()
def infisical_brain(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_PATH", str(tmp_path))
    (tmp_path / "_system").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_cache_roundtrip_is_actually_encrypted_on_disk(infisical_brain, monkeypatch):
    monkeypatch.setenv("INFISICAL_CACHE_KEY", Fernet.generate_key().decode())

    il._write_cache({"SECRET_KEY": "abc123"})

    raw = il._cache_file().read_bytes()
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)

    assert il._load_cache() == {"SECRET_KEY": "abc123"}


def test_cache_roundtrip_stays_plaintext_without_a_key(infisical_brain, monkeypatch):
    monkeypatch.delenv("INFISICAL_CACHE_KEY", raising=False)

    il._write_cache({"SECRET_KEY": "abc123"})

    raw = il._cache_file().read_text()
    data = json.loads(raw)  # must not raise — proves graceful plaintext fallback
    assert data["secrets"] == {"SECRET_KEY": "abc123"}

    assert il._load_cache() == {"SECRET_KEY": "abc123"}


def test_legacy_plaintext_cache_migrates_in_place_once_a_key_exists(infisical_brain, monkeypatch):
    monkeypatch.delenv("INFISICAL_CACHE_KEY", raising=False)
    il._cache_file().write_text(
        json.dumps({"fetched_at": "2026-01-01T00:00:00Z", "secrets": {"FOO": "bar"}})
    )

    monkeypatch.setenv("INFISICAL_CACHE_KEY", Fernet.generate_key().decode())

    assert il._load_cache() == {"FOO": "bar"}

    raw = il._cache_file().read_bytes()
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)  # now encrypted on disk after the self-heal read


def test_read_cache_public_reader_matches_internal_loader(infisical_brain, monkeypatch):
    monkeypatch.setenv("INFISICAL_CACHE_KEY", Fernet.generate_key().decode())
    il._write_cache({"WORKFLOWS_TOKEN": "tok"})

    envelope = il.read_cache()
    assert envelope["secrets"] == {"WORKFLOWS_TOKEN": "tok"}
    assert "fetched_at" in envelope


def test_read_cache_returns_empty_dict_when_missing(infisical_brain, monkeypatch):
    monkeypatch.setenv("INFISICAL_CACHE_KEY", Fernet.generate_key().decode())
    assert il.read_cache() == {}


def test_token_file_roundtrip_encrypted_and_resolved(infisical_brain, monkeypatch):
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)
    monkeypatch.setenv("INFISICAL_CACHE_KEY", Fernet.generate_key().decode())

    il.save_token_to_file("sf-token-xyz")

    raw = il._config_file().read_bytes()
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)

    token, source = il._resolve_token()
    assert token == "sf-token-xyz"
    assert source == "file"


def test_legacy_plaintext_token_file_migrates_in_place(infisical_brain, monkeypatch):
    monkeypatch.delenv("INFISICAL_TOKEN", raising=False)
    monkeypatch.delenv("INFISICAL_CACHE_KEY", raising=False)
    il._config_file().write_text(json.dumps({"token": "old-plaintext-token"}))

    monkeypatch.setenv("INFISICAL_CACHE_KEY", Fernet.generate_key().decode())

    token, source = il._resolve_token()
    assert token == "old-plaintext-token"
    assert source == "file"

    raw = il._config_file().read_bytes()
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)


def test_invalid_cache_key_falls_back_to_plaintext_instead_of_crashing(
    infisical_brain, monkeypatch
):
    monkeypatch.setenv("INFISICAL_CACHE_KEY", "not-a-valid-fernet-key")

    il._write_cache({"SECRET_KEY": "abc123"})  # must not raise

    raw = il._cache_file().read_text()
    assert json.loads(raw)["secrets"] == {"SECRET_KEY": "abc123"}
    assert il._load_cache() == {"SECRET_KEY": "abc123"}


def test_n8n_sync_business_workflows_reads_credentials_through_encrypted_cache(
    infisical_brain, monkeypatch, caplog
):
    """n8n_service.py bypassed infisical_loader entirely before this change,
    reading infisical_cache.json off disk directly — which would silently
    break (get back {}) once the cache is encrypted. Confirms the switch to
    infisical_loader.read_cache() actually resolves real credentials, by
    checking the function does NOT take its 'credentials absent' early-return
    branch (which it would if read_cache() came back empty)."""
    monkeypatch.setenv("INFISICAL_CACHE_KEY", Fernet.generate_key().decode())
    il._write_cache({"WORKFLOWS_BASE_URL": "https://workflows.example.com", "WORKFLOWS_TOKEN": "t"})

    import services.n8n_service as n8n

    # Short-circuit before any real file/network I/O by forcing "no stubs
    # found" — a distinct early-return branch from the credentials check.
    monkeypatch.setattr(n8n, "STUBS_DIR", infisical_brain / "no_stubs_here")

    with caplog.at_level("DEBUG", logger="logcore.n8n"):
        result = n8n.sync_business_workflows()

    assert not any("absent from Infisical cache" in r.message for r in caplog.records)
    assert any("No workflow stubs found" in r.message for r in caplog.records)
    assert result == {"created": 0, "updated": 0, "deleted": 0, "skipped": 0, "errors": []}
