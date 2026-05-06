from datetime import timedelta
from uuid import uuid4

import pytest

from cloud_app.auth.jwt import JwtPayload, issue_token, verify_token


def test_issue_then_verify_roundtrips_payload():
    user_id = uuid4()
    token = issue_token(JwtPayload(sub=str(user_id), tier="operations", role="admin"),
                        secret="testsecret", lifetime=timedelta(hours=24))
    payload = verify_token(token, secret="testsecret")
    assert payload.sub == str(user_id)
    assert payload.tier == "operations"
    assert payload.role == "admin"


def test_verify_rejects_wrong_secret():
    token = issue_token(JwtPayload(sub="x", tier="operations", role="admin"),
                        secret="a", lifetime=timedelta(hours=24))
    with pytest.raises(Exception):                 # PyJWT raises InvalidSignatureError
        verify_token(token, secret="b")


def test_verify_rejects_expired_token():
    token = issue_token(JwtPayload(sub="x", tier="operations", role="admin"),
                        secret="s", lifetime=timedelta(seconds=-1))
    with pytest.raises(Exception):                 # ExpiredSignatureError
        verify_token(token, secret="s")
