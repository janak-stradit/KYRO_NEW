"""
tests/api/test_screening_identifiers.py — Passport, national ID, registration and
IMO numbers: read from each list, held for customers and owners, and used in matching.
"""
from datetime import date

import pytest

from app.services.screening_service import normalize_name, screen_customer, screening_baseline, search_columns, subject_identifiers
from app.models.watchlist import WatchlistEntity
from app.services.watchlist_adapters.base import identifier, identifier_type
from app.services.watchlist_adapters.ofac import parse_ofac_xml
from app.services.watchlist_adapters.uk_ofsi import parse_uk_ofsi_csv
from app.services.watchlist_adapters.un import parse_un_xml
from tests.api.test_screening_service import _make_customer, _make_source

_OFAC = b"""<?xml version="1.0"?>
<sdnList xmlns="http://tempuri.org/sdnList.xsd">
  <sdnEntry>
    <uid>2001</uid><firstName>Ivan</firstName><lastName>Example</lastName><sdnType>Individual</sdnType>
    <idList>
      <id><uid>1</uid><idType>Passport</idType><idNumber>AB 123-456</idNumber><idCountry>Testland</idCountry></id>
      <id><uid>2</uid><idType>National ID No.</idType><idNumber>99887766</idNumber></id>
    </idList>
  </sdnEntry>
</sdnList>"""

_UN = b"""<?xml version="1.0"?>
<CONSOLIDATED_LIST><INDIVIDUALS><INDIVIDUAL>
  <DATAID>9</DATAID><REFERENCE_NUMBER>QDi.999</REFERENCE_NUMBER><FIRST_NAME>Omar</FIRST_NAME><SECOND_NAME>Sample</SECOND_NAME>
  <INDIVIDUAL_DOCUMENT><TYPE_OF_DOCUMENT>Passport</TYPE_OF_DOCUMENT><NUMBER>P7654321</NUMBER><ISSUING_COUNTRY>Testland</ISSUING_COUNTRY></INDIVIDUAL_DOCUMENT>
</INDIVIDUAL></INDIVIDUALS></CONSOLIDATED_LIST>"""

_OFSI = (
    "Name 6,Name 1,Group ID,Group Type,Passport Number,National Identification Number,Company Number\n"
    "Sample,Olga,555,Individual,X1234567,NI-998877,\n"
    "Shipping Ltd,Blue,556,Entity,,,C0012345\n"
).encode()


# ── Reading identifiers from each list (no database) ─────────────────────

def test_each_list_yields_its_identifiers():
    ofac = next(parse_ofac_xml(_OFAC))
    assert {(i["type"], i["normalized"]) for i in ofac.identifiers} == {("PASSPORT", "AB123456"), ("NATIONAL_ID", "99887766")}
    un = next(parse_un_xml(_UN))
    assert [(i["type"], i["normalized"], i["country"]) for i in un.identifiers] == [("PASSPORT", "P7654321", "Testland")]
    ofsi = {r.external_id: r for r in parse_uk_ofsi_csv(_OFSI)}
    assert {(i["type"], i["normalized"]) for i in ofsi["555"].identifiers} == {("PASSPORT", "X1234567"), ("NATIONAL_ID", "NI998877")}
    assert [(i["type"], i["normalized"]) for i in ofsi["556"].identifiers] == [("REGISTRATION", "C0012345")]


@pytest.mark.parametrize("label, kind", [
    ("Passport", "PASSPORT"), ("National ID No.", "NATIONAL_ID"), ("Tax ID No.", "TAX_ID"), ("Registration Number", "REGISTRATION"),
    ("IMO 9187629", "IMO"), ("Driver's License No.", "OTHER"), ("Continental reference", "OTHER"),
])
def test_identifier_labels_map_to_types(label, kind):
    assert identifier_type(label) == kind


def test_customer_identifiers_come_from_metadata_and_record_fields():
    found = subject_identifiers({"registration_number": "B1234567", "documents": [{"passport_no": "ab 12-3456"}], "risk": "HIGH"},
                                ("Passport", "X9876543"))
    assert {(i["type"], i["normalized"]) for i in found} == {("REGISTRATION", "B1234567"), ("PASSPORT", "AB123456"), ("PASSPORT", "X9876543")}
    assert identifier("Passport", "12") is None  # too short to compare


# ── Matching with identifiers ────────────────────────────────────────────

def _entity(db_session, source, name, identifiers, **extra):
    entity = WatchlistEntity(
        source_id=source.id, external_id=name[:20], entity_type="INDIVIDUAL", primary_name=name, normalized_name=normalize_name(name),
        identifiers=identifiers, identifier_values=sorted({i["normalized"] for i in identifiers}) or None,
        **search_columns(name, None), **extra,
    )
    db_session.add(entity)
    db_session.flush()
    return entity


@pytest.mark.db
def test_the_same_passport_finds_the_entry_even_under_another_name(db_session):
    source = _make_source(db_session)
    listed = _entity(db_session, source, "Abu Rami", [identifier("Passport", "AB123456")])
    customer = _make_customer(db_session, full_name="Rami Haddad", email="id.match@example.com",
                              customer_metadata={"passport_number": "ab 123 456"})

    results = screen_customer(db_session, customer)
    assert [r.watchlist_entity_id for r in results] == [listed.id]
    assert results[0].match_status == "POTENTIAL_MATCH"  # a number alone is for an analyst to confirm
    assert results[0].match_details["identifier_match"] == "PASSPORT ab 123 456"


@pytest.mark.db
def test_a_matching_number_strengthens_a_name_match_to_confirmed(db_session):
    # 86.7 on the name alone: a potential match; the same passport makes it confirmed
    source = _make_source(db_session)
    _entity(db_session, source, "Vladimir Petrov", [identifier("Passport", "P5550001")])
    customer = _make_customer(db_session, full_name="Vladimer Petrof", email="id.boost@example.com",
                              customer_metadata={"passport_number": "P5550001"})
    results = screen_customer(db_session, customer)
    assert results[0].match_status == "CONFIRMED_MATCH" and customer.sanctions_flag


@pytest.mark.db
def test_a_different_number_of_the_same_kind_weakens_the_match_and_is_flagged(db_session):
    source = _make_source(db_session)
    _entity(db_session, source, "Vladimir Petrov", [identifier("Passport", "P5550001")], date_of_birth=date(1970, 1, 1))
    customer = _make_customer(db_session, full_name="Vladimir Petrov", email="id.conflict@example.com", date_of_birth=date(1970, 1, 1),
                              customer_metadata={"passport_number": "Z0000009"})
    results = screen_customer(db_session, customer)
    assert results[0].match_status == "POTENTIAL_MATCH" and not customer.sanctions_flag  # was confirmed on name + DOB alone
    assert "Z0000009" in results[0].match_details["identifier_conflict"]


@pytest.mark.db
def test_baseline_counts_without_writing(db_session):
    source = _make_source(db_session)
    _entity(db_session, source, "Abu Rami", [identifier("Passport", "AB123456")])
    _make_customer(db_session, full_name="Rami Haddad", email="baseline@example.com", customer_metadata={"passport_number": "AB123456"})

    report = screening_baseline(db_session, limit=50)
    assert report["customers_with_identifier_match"] >= 1
    assert report["with_current_policy"]["potential"] >= 1
