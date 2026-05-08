import re
from datetime import UTC, datetime

from edge_agent.now import now_utc


def test_now_utc_is_rfc3339_millisecond_z():
    value = now_utc()

    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", value)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert abs((parsed - datetime.now(UTC)).total_seconds()) < 5
