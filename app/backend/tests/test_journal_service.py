"""Tests for services/journal_service.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import services.journal_service as svc

USER = "TestUser"


@pytest.fixture()
def journal_dir(brain):
    d = brain / "USERS" / USER / "Journal"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# list_entries
# ---------------------------------------------------------------------------


def test_list_entries_empty(brain):
    assert svc.list_entries(USER) == []


def test_list_entries_returns_date_and_preview(journal_dir):
    svc.upsert_entry(USER, "2024-06-01", "First line\nSecond line")
    entries = svc.list_entries(USER)
    assert len(entries) == 1
    assert entries[0]["date"] == "2024-06-01"
    assert entries[0]["preview"] == "First line"


def test_list_entries_most_recent_first(journal_dir):
    for date in ["2024-06-01", "2024-06-03", "2024-06-02"]:
        svc.upsert_entry(USER, date, f"entry {date}")
    dates = [e["date"] for e in svc.list_entries(USER)]
    assert dates == sorted(dates, reverse=True)


def test_list_entries_ignores_non_date_files(journal_dir):
    (journal_dir / "README.md").write_text("not a journal entry")
    svc.upsert_entry(USER, "2024-06-01", "real entry")
    assert len(svc.list_entries(USER)) == 1


def test_list_entries_skips_empty_lines_for_preview(journal_dir):
    svc.upsert_entry(USER, "2024-06-01", "\n\nActual content")
    entry = svc.list_entries(USER)[0]
    assert entry["preview"] == "Actual content"


# ---------------------------------------------------------------------------
# get_entry
# ---------------------------------------------------------------------------


def test_get_entry_success(journal_dir):
    svc.upsert_entry(USER, "2024-06-15", "Hello journal")
    result = svc.get_entry(USER, "2024-06-15")
    assert result is not None
    assert result["content"] == "Hello journal"
    assert result["date"] == "2024-06-15"


def test_get_entry_not_found(journal_dir):
    assert svc.get_entry(USER, "2024-01-01") is None


# ---------------------------------------------------------------------------
# upsert_entry
# ---------------------------------------------------------------------------


def test_upsert_creates_file(journal_dir):
    svc.upsert_entry(USER, "2024-06-20", "content")
    assert (journal_dir / "2024-06-20.md").exists()


def test_upsert_updates_existing(journal_dir):
    svc.upsert_entry(USER, "2024-06-20", "v1")
    result = svc.upsert_entry(USER, "2024-06-20", "v2")
    assert result["content"] == "v2"
    assert svc.get_entry(USER, "2024-06-20")["content"] == "v2"


# ---------------------------------------------------------------------------
# delete_entry
# ---------------------------------------------------------------------------


def test_delete_entry_success(journal_dir):
    svc.upsert_entry(USER, "2024-06-10", "to delete")
    assert svc.delete_entry(USER, "2024-06-10") is True
    assert not (journal_dir / "2024-06-10.md").exists()


def test_delete_entry_not_found(journal_dir):
    assert svc.delete_entry(USER, "2024-01-01") is False


# ---------------------------------------------------------------------------
# Date validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_date", [
    "June 1 2024",
    "20240601",
    "2024/06/01",
    "not-a-date",
    "",
])
def test_invalid_date_raises(journal_dir, bad_date):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        svc.upsert_entry(USER, bad_date, "content")


@pytest.mark.parametrize("bad_date", [
    "June 1 2024",
    "20240601",
])
def test_invalid_date_get_raises(journal_dir, bad_date):
    with pytest.raises(ValueError):
        svc.get_entry(USER, bad_date)
