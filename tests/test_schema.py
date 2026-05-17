"""Tests for Grist type → Shillelagh field mapping."""
import pytest
from shillelagh.fields import Boolean, DateTime, Float, Integer, String

from shillelagh_gristapi.schema import Reference, ReferenceList, map_grist_type


@pytest.mark.parametrize(
    "grist_type, expected_class",
    [
        ("Text", String),
        ("text", String),
        ("TEXT", String),
        ("Numeric", Float),
        ("numeric", Float),
        ("Int", Integer),
        ("Integer", Integer),
        ("Bool", Boolean),
        ("bool", Boolean),
        ("Date", DateTime),
        ("date", DateTime),
        ("DateTime:America/New_York", DateTime),
        ("datetime:UTC", DateTime),
        ("Choice", String),
        ("choice", String),
        ("ChoiceList", String),
        ("choicelist", String),
        ("Attachments", String),
        ("attachments", String),
    ],
)
def test_map_grist_type_basic(grist_type, expected_class):
    assert isinstance(map_grist_type(grist_type), expected_class)


@pytest.mark.parametrize("ref_type", ["Ref:Table1", "ref:OtherTable", "Ref:"])
def test_map_grist_type_reference(ref_type):
    assert isinstance(map_grist_type(ref_type), Reference)


@pytest.mark.parametrize("ref_type", ["RefList:Table1", "reflist:OtherTable", "RefList:"])
def test_map_grist_type_referencelist(ref_type):
    assert isinstance(map_grist_type(ref_type), ReferenceList)


def test_map_grist_type_unknown_falls_back_to_string():
    assert isinstance(map_grist_type("SomeUnknownType"), String)


def test_map_grist_type_none_falls_back_to_string():
    assert isinstance(map_grist_type(None), String)


def test_map_grist_type_empty_string_falls_back_to_string():
    assert isinstance(map_grist_type(""), String)


def test_reference_field_types():
    ref = Reference()
    assert ref.type == "TEXT"
    assert ref.db_api_type == "TEXT"


def test_referencelist_field_types():
    ref = ReferenceList()
    assert ref.type == "TEXT"
    assert ref.db_api_type == "TEXT"
