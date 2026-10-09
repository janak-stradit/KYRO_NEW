"""
tests/app/test_screening_service.py — screen_customer confirmed/potential
match thresholds and the conservative auto-flag policy (only a near-exact
match auto-sets sanctions_flag; weaker matches queue for analyst review).
"""
from datetime import date

import pytest

from app.models.customer import Customer
from app.models.watchlist import WatchlistEntity, WatchlistSource
from app.services.screening_service import screen_customer

pytestmark = pytest.mark.db


def _make_source(db_session) -> WatchlistSource:
    source = WatchlistSource(
        code="OFAC_SDN", name="Test Source", list_category="SANCTIONS", url="http://example.test/sdn.xml"
    )
    db_session.add(source)
    db_session.flush()
    return source


def _make_entity(db_session, source, **overrides) -> WatchlistEntity:
    defaults = dict(
        source_id=source.id,
        external_id=overrides.pop("external_id", "9001"),
        entity_type="INDIVIDUAL",
        primary_name="Vladimir Petrov",
        normalized_name="VLADIMIR PETROV",
        date_of_birth=date(1970, 1, 1),
    )
    defaults.update(overrides)
    entity = WatchlistEntity(**defaults)
    db_session.add(entity)
    db_session.flush()
    return entity


def _make_customer(db_session, **overrides) -> Customer:
    defaults = dict(full_name="Vladimir Petrov", email=overrides.pop("email", "screen@example.com"))
    defaults.update(overrides)
    customer = Customer(**defaults)
    db_session.add(customer)
    db_session.flush()
    return customer


def test_exact_name_and_dob_match_auto_confirms_and_flags(db_session):
    source = _make_source(db_session)
    entity = _make_entity(db_session, source)
    customer = _make_customer(db_session, date_of_birth=date(1970, 1, 1))

    results = screen_customer(db_session, customer)

    assert len(results) == 1
    assert results[0].match_status == "CONFIRMED_MATCH"
    assert results[0].watchlist_entity_id == entity.id
    assert customer.sanctions_flag is True
    assert customer.last_screened_at is not None


def test_weak_name_match_is_potential_only_and_does_not_flag(db_session):
    # "Vlad Petrovsky" vs "Vladimir Petrov" scores ~76 as whole names —
    # above the 75 potential-match floor but well short of the 92 confirmed
    # floor, so it must queue for review without touching sanctions_flag.
    source = _make_source(db_session)
    _make_entity(db_session, source)
    customer = _make_customer(db_session, full_name="Vlad Petrovsky", email="weak.match@example.com")

    results = screen_customer(db_session, customer)

    assert len(results) == 1
    assert results[0].match_status == "POTENTIAL_MATCH"
    assert 75 <= float(results[0].match_score) < 92
    assert customer.sanctions_flag is False


def test_unrelated_name_produces_no_screening_row(db_session):
    source = _make_source(db_session)
    _make_entity(db_session, source)
    customer = _make_customer(db_session, full_name="Jane Doe", email="unrelated@example.com")

    results = screen_customer(db_session, customer)

    assert results == []
    assert customer.sanctions_flag is False
    assert customer.last_screened_at is not None


def test_inactive_entity_is_not_matched(db_session):
    source = _make_source(db_session)
    _make_entity(db_session, source, is_active=False)
    customer = _make_customer(db_session)

    results = screen_customer(db_session, customer)

    assert results == []
