from cloud_app.auth.passwords import hash_password, verify_password


def test_hash_then_verify_roundtrip():
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("hunter2")
    assert verify_password("wrong", h) is False


def test_hash_produces_different_hashes_for_same_password():
    """Salt is per-call; two hashes of the same plaintext differ."""
    assert hash_password("p") != hash_password("p")
