from model import *
from grammar import *
import pytest


@pytest.mark.parametrize('text, term', [
    ('a', Atom('a')),
    ('b', Atom('b')),
    ('z', Atom('z')),
    ('a123', Atom('a123')),
    (':', Atom(':')),
    (':-', Atom(':-')),
])
def test_parse_term(text, term):
    assert parse_term(text) == term
