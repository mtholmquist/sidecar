from sidecar.utils.redact import redact


def test_redact_nested_payload_preserves_public_context():
    payload = {
        "target": "Public host 8.8.8.8 talks to 192.168.1.10",
        "auth": ["api_key='abcdef1234567890'", "Bearer token.value-123"],
        "nested": {"secret": "secret_key=my-super-secret-value"},
    }

    redacted = redact(payload)

    assert "8.8.8.8" in redacted["target"]
    assert "<IP_PRIV>" in redacted["target"]
    assert redacted["auth"] == ["<API_KEY>", "<TOKEN>"]
    assert redacted["nested"]["secret"] == "<SECRET>"


def test_redact_allow_cloud_returns_original_payload():
    payload = {"password": "password='hunter2'"}

    assert redact(payload, allow_cloud=True) is payload
