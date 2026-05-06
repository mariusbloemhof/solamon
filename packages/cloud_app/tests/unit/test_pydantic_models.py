"""Sanity-test the Pydantic models — they must round-trip the openapi.yaml shapes."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from cloud_app.models.pydantic import (
    CommandIssue, ControlCommand, DeviceSnapshot, LoginRequest, LoginResponse,
    SiteSummary, User,
)


def test_login_request_requires_email_and_password():
    with pytest.raises(ValidationError):
        LoginRequest.model_validate({"email": "a@b.c"})


def test_user_round_trips_required_fields():
    u = User(id=uuid4(), email="a@b.c", display_name="A",
             tier="operations", role="admin")
    assert u.model_dump()["tier"] == "operations"


def test_login_response_carries_user():
    u = User(id=uuid4(), email="a@b.c", display_name="A",
             tier="operations", role="admin")
    r = LoginResponse(access_token="t", token_type="bearer",
                      expires_in=86400, user=u)
    assert r.token_type == "bearer"


def test_command_issue_validates_type():
    with pytest.raises(ValidationError):
        CommandIssue(logical_metric="x", type="invalid", parameters={})


def test_device_snapshot_metrics_accepts_arbitrary_values():
    s = DeviceSnapshot(snapshot_time=datetime.now(timezone.utc),
                       metrics={"active_power_total": 12.35, "current_wiring_type": "3CT"})
    assert s.metrics["active_power_total"] == 12.35


def test_control_command_serialises_status_enum():
    c = ControlCommand(
        id=uuid4(), device_id=uuid4(), logical_metric="demand_window_minutes",
        type="set_value", parameters={"value": 30}, status="sent",
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc),
    )
    assert c.model_dump()["status"] == "sent"
