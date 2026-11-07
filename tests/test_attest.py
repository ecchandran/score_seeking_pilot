import pytest

from src.attest import parse


@pytest.mark.parametrize("raw,want", [
    ("Yes", "yes"), ("No.", "no"), ("yes", "yes"), ("NO", "no"), ("  Yes\n", "yes"),
    ("**Yes**", "yes"), ('"No"', "no"), ("Yes.", "yes"),
    ("Yes, I followed them.", "unparsed"), ("I think so", "unparsed"), ("Yes/No", "unparsed"),
    ("", "unparsed"), (None, "unparsed"), ("Yesterday", "unparsed"),
])
def test_parse(raw, want):
    assert parse(raw) == want
