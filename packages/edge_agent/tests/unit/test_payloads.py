from edge_agent.config import BootstrapConfig
from edge_agent.payloads import EdgeSample, build_acuvim_native_payload, build_heartbeat


def _config() -> BootstrapConfig:
    return BootstrapConfig(
        schema_version="1.0",
        site_slug="bench",
        cloud_url="https://cloud.amendi.dev",
        bearer_token="secret",
        device_host="192.168.1.254",
        device_unit_id=1,
    )


def test_heartbeat_matches_mqtt_contract_shape():
    payload = build_heartbeat(_config(), EdgeSample(1, "2026-05-08T12:00:00.000Z"))

    assert payload["version"] == "1.0"
    assert payload["site_slug"] == "bench"
    assert payload["status"] == "online"
    assert payload["buffer_depth_seconds"] == 0
    assert payload["halted_blocks"] == []


def test_acuvim_native_payload_matches_current_cloud_adapter():
    payload = build_acuvim_native_payload(
        _config(),
        EdgeSample(1, "2026-05-08T12:00:00.000Z"),
    )

    params = {row["param"] for row in payload["readings"]}
    assert payload["timestamp"] == "2026-05-08T12:00:00.000Z"
    assert payload["device"]["model"] == "Acuvim L"
    assert {"V1", "V2", "V3", "I1", "I2", "I3", "Psum", "PF", "Freq_Hz"} <= params
