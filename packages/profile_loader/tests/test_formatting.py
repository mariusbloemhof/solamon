from profile_loader import ADDRESS_FIELDS, format_address


def test_format_address_basic():
    assert format_address(0x0600) == "0x0600"


def test_format_address_pads_to_4_digits():
    assert format_address(5) == "0x0005"


def test_format_address_uppercase():
    assert format_address(0xC350) == "0xC350"


def test_format_address_handles_large_values():
    assert format_address(0x10000) == "0x10000"


def test_address_fields_is_frozenset():
    assert isinstance(ADDRESS_FIELDS, frozenset)
    assert "address" in ADDRESS_FIELDS
