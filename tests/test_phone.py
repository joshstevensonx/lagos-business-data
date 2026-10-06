"""SPEC §6.1 - clean_phone went through three corrections; these pin it."""
import pytest

from lagosdata.normalise import clean_phone


@pytest.mark.parametrize('raw, want', [
    ('0803 123 4567', '+2348031234567'),
    ('+234 803 123 4567', '+2348031234567'),
    ('234 1 234 5678', '+23412345678'),
    ('08031234567', '+2348031234567'),
    ('01 2345678', '+23412345678'),
    ('+23412454213789', ''),                       # garbage that passed an earlier version
    ('0803-123-456', ''),                          # 9 digits: plausible-looking and useless
    ('0803 123 4567 / 0805 987 6543', '+2348031234567'),   # first valid wins
    ('WhatsApp: 0803 123 4567', '+2348031234567'),
    ('', ''),
    (None, ''),
])
def test_clean_phone(raw, want):
    assert clean_phone(raw) == want


def test_mobile_is_always_ten_digits_after_country_code():
    # the [789]\d (9-digit) bug: every mobile result must be +234 + 10 digits
    for raw in ['0703 000 0000', '0901-234-5678', '+2348123456789', '2349012345678']:
        out = clean_phone(raw)
        assert out.startswith('+234') and len(out) == 14, (raw, out)
