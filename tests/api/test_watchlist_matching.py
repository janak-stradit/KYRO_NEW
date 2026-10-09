"""
tests/app/test_watchlist_matching.py — normalize_name/score_match unit tests.
No DB required: WatchlistEntity is only used as an in-memory value holder.
"""
from datetime import date

import pytest

from app.models.watchlist import WatchlistEntity
from app.services.screening_service import normalize_name, score_match


def _entity(**overrides) -> WatchlistEntity:
    defaults = dict(primary_name="Vladimir Petrov", aka_names=[], date_of_birth=None)
    defaults.update(overrides)
    return WatchlistEntity(**defaults)


def test_normalize_name_strips_punctuation_and_case():
    assert normalize_name("O'Brien-Smith Jr.") == "OBRIEN SMITH JR"
    assert normalize_name("  Multiple   Spaces  ") == "MULTIPLE SPACES"


def test_normalize_name_strips_diacritics():
    assert normalize_name("José Núñez") == "JOSE NUNEZ"


def test_score_match_exact_name_scores_high():
    entity = _entity(primary_name="Vladimir Petrov")
    result = score_match("Vladimir Petrov", None, entity)
    assert result.score >= 95


def test_score_match_dob_boosts_score():
    entity = _entity(primary_name="Vladimir Petrov", date_of_birth=date(1970, 5, 1))
    without_dob = score_match("Vladimir Petrov", None, entity)
    with_dob = score_match("Vladimir Petrov", date(1970, 5, 1), entity)
    assert with_dob.score >= without_dob.score
    assert with_dob.dob_match is True


def test_score_match_unrelated_name_scores_low():
    entity = _entity(primary_name="Vladimir Petrov")
    result = score_match("Jane Doe", None, entity)
    assert result.score < 50


def test_score_match_prefers_best_alias():
    entity = _entity(primary_name="Some Registered Entity Name", aka_names=["Alpha Trading Co"])
    result = score_match("Alpha Trading Co", None, entity)
    assert result.matched_name == "Alpha Trading Co"
    assert result.score >= 95


@pytest.mark.parametrize("customer, listed", [
    ("Jordan Mcdaniel", "DANIEL"),                      # the list entry is a fragment of the customer's surname
    ("James Martinez", "Javier ABAUNZA MARTINEZ"),      # only the surname is shared
    ("Emily Roberts", "EMILY S"),                       # only the given name is shared
    ("Vanessa Fernandez", "Dora Vanessa VALDEZ FERNANDEZ"),
    ("John James", "Jeffrey John James ASHFIELD"),      # the whole name sits inside a longer, different one
    ("Richard Lloyd", "Richard YUE"),                   # short names: same given name, unrelated surname
    ("Sarah Ho", "SARAH"),                              # a one-word list entry against a full name
    ("Sara Taylor", "Mark TAYLOR"),
])
def test_partial_name_overlap_is_not_a_match(customer, listed):
    assert score_match(customer, None, _entity(primary_name=listed)).score < 75


@pytest.mark.parametrize("customer, listed, low, high", [
    ("John Smith", "John Michael Smith", 85, 92),       # one extra part: review, never auto-confirm
    ("Petrov Vladimir", "Vladimir Petrov", 100, 100),   # word order does not matter
    ("Sergei Ivanov", "Sergey Ivanov", 90, 100),        # transliteration variants
    ("Mohammed Al Rashid", "Muhammad Al-Rashid", 85, 100),
])
def test_same_name_in_another_form_still_matches(customer, listed, low, high):
    assert low <= score_match(customer, None, _entity(primary_name=listed)).score <= high


def test_close_but_different_names_stay_for_review_only():
    """One letter apart is worth an analyst's look, and is never auto-confirmed without more."""
    score = score_match("Mary Taylor", None, _entity(primary_name="Mark TAYLOR")).score
    assert 75 <= score < 92
