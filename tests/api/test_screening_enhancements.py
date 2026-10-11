"""
tests/api/test_screening_enhancements.py — Transliteration, spelling variants,
phonetic matching, alias search and screening thresholds as policy.
"""
from datetime import date

import pytest

from app.models.rule_config import RuleConfig
from app.models.watchlist import WatchlistEntity
from app.services import rule_config_service
from app.services.screening_service import name_score, normalize_name, screen_customer, search_columns
from tests.api.test_screening_service import _make_customer, _make_source


# ── Name comparison (no database) ────────────────────────────────────────

def test_other_scripts_are_transliterated_before_matching():
    assert normalize_name("Владимир Путин") == "VLADIMIR PUTIN"
    assert name_score("Владимир Путин", "Vladimir PUTIN") == 100
    assert normalize_name("José Núñez") == "JOSE NUNEZ"  # unchanged behaviour for accented Latin names


def test_spelling_variants_of_one_name_match():
    assert name_score("Mohamed Hassan", "Muhammad Hasan") >= 90
    assert name_score("Youssef Karimi", "Yusuf Karimi") == 100


def test_names_that_sound_the_same_go_to_review_but_never_confirm():
    score = name_score("Jon Smyth", "John Smith")
    assert 75 <= score < 92
    assert name_score("Catherine Zeta", "Kathryn Zeta") == 85
    # Turned off by policy, sound alone no longer lifts the score
    assert name_score("Catherine Zeta", "Kathryn Zeta", phonetic_score=0) < 85


@pytest.mark.parametrize("customer, listed", [
    ("Jordan Mcdaniel", "DANIEL"),
    ("Richard Lloyd", "Richard YUE"),
    ("Sara Taylor", "Mark TAYLOR"),
    ("Emily Roberts", "EMILY S"),
])
def test_sound_does_not_turn_partial_overlaps_into_matches(customer, listed):
    assert name_score(customer, listed) < 75


# ── Screening against the list ───────────────────────────────────────────

def _entity(db_session, source, primary_name, aka_names=None, **extra):
    entity = WatchlistEntity(
        source_id=source.id, external_id=extra.pop("external_id", primary_name[:20]), entity_type="INDIVIDUAL",
        primary_name=primary_name, normalized_name=normalize_name(primary_name), aka_names=aka_names,
        **search_columns(primary_name, aka_names), **extra,
    )
    db_session.add(entity)
    db_session.flush()
    return entity


@pytest.mark.db
def test_an_alias_is_found_even_when_the_primary_name_is_unlike(db_session):
    source = _make_source(db_session)
    listed = _entity(db_session, source, "Global Maritime Holdings Limited", aka_names=["Seastar Shipping"])
    customer = _make_customer(db_session, full_name="Seastar Shipping", email="alias@example.com", customer_type="CORPORATE")

    results = screen_customer(db_session, customer)
    assert [r.watchlist_entity_id for r in results] == [listed.id]
    assert results[0].match_details["matched_name"] == "Seastar Shipping"


@pytest.mark.db
def test_a_name_that_sounds_alike_is_found_and_left_for_review(db_session):
    source = _make_source(db_session)
    # Spelt too differently to be found by spelling (69.6 without sound), found by how it sounds
    listed = _entity(db_session, source, "Filip Nite", date_of_birth=date(1970, 1, 1))
    customer = _make_customer(db_session, full_name="Philip Knight", email="sound@example.com")

    results = screen_customer(db_session, customer)
    assert [r.watchlist_entity_id for r in results] == [listed.id]
    assert results[0].match_status == "POTENTIAL_MATCH" and not customer.sanctions_flag


@pytest.mark.db
def test_a_name_in_another_script_is_found(db_session):
    source = _make_source(db_session)
    listed = _entity(db_session, source, "Vladimir PUTIN", date_of_birth=date(1952, 10, 7))
    customer = _make_customer(db_session, full_name="Владимир Путин", email="cyrillic@example.com", date_of_birth=date(1952, 10, 7))

    results = screen_customer(db_session, customer)
    assert [r.watchlist_entity_id for r in results] == [listed.id]
    assert results[0].match_status == "CONFIRMED_MATCH" and customer.sanctions_flag


@pytest.mark.db
def test_thresholds_are_policy(db_session):
    source = _make_source(db_session)
    _entity(db_session, source, "Filip Nite")
    customer = _make_customer(db_session, full_name="Philip Knight", email="policy@example.com")
    assert len(screen_customer(db_session, customer)) == 1

    # Phonetic matching off: the sound-alike name is no longer even a potential match
    db_session.add(RuleConfig(key="SCREENING_PHONETIC_SCORE", jurisdiction="GLOBAL", value={"value": 0}, is_active=True))
    db_session.flush()
    rule_config_service.invalidate_cache()
    assert screen_customer(db_session, customer) == []
