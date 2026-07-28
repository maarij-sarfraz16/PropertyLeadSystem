from app.pipeline.normalize import normalize_phone


def test_local_mobile_to_e164():
    assert normalize_phone("0300-1234567") == "+923001234567"


def test_spaced_mobile():
    assert normalize_phone("0321 9876543") == "+923219876543"


def test_landline_lahore():
    assert normalize_phone("042-35551234") == "+924235551234"


def test_already_international():
    assert normalize_phone("+92 345 1122334") == "+923451122334"


def test_none_and_garbage():
    assert normalize_phone(None) is None
    assert normalize_phone("not a phone") is None
