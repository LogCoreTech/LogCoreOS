"""Tests for services/tags_service.py — the shared Goals+Tasks tag
vocabulary (2026-08-29)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import tags_service

USER = "Alice"


def test_register_new_tags(brain):
    result = tags_service.register_tags(USER, "personal", ["urgent", "family"])
    assert result == ["urgent", "family"]
    assert tags_service.get_tags(USER, "personal") == ["urgent", "family"]


def test_register_is_a_union_add_not_a_replace(brain):
    tags_service.register_tags(USER, "personal", ["urgent"])
    tags_service.register_tags(USER, "personal", ["family"])
    assert tags_service.get_tags(USER, "personal") == ["urgent", "family"]


def test_register_deduplicates_case_insensitively_keeping_first_casing(brain):
    tags_service.register_tags(USER, "personal", ["Urgent"])
    tags_service.register_tags(USER, "personal", ["urgent", "URGENT"])
    assert tags_service.get_tags(USER, "personal") == ["Urgent"]


def test_personal_and_pool_vocabularies_are_separate(brain):
    tags_service.register_tags(USER, "personal", ["solo"])
    tags_service.register_tags("_household", "personal", ["family-shared"])
    assert tags_service.get_tags(USER, "personal") == ["solo"]
    assert tags_service.get_tags("_household", "personal") == ["family-shared"]


def test_empty_input_is_a_noop(brain):
    tags_service.register_tags(USER, "personal", [])
    assert tags_service.get_tags(USER, "personal") == []


def test_get_tags_empty_by_default(brain):
    assert tags_service.get_tags("NoOneYet", "personal") == []
