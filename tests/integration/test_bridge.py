# test_bridge.py - FIXED Tests
import pytest
from fastapi.testclient import TestClient
from main import app, PROCESSED_MESSAGES, IN_MEMORY_LOG

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup():
    PROCESSED_MESSAGES.clear()
    IN_MEMORY_LOG.clear()
    yield


class TestHealth:
    def test_health_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["service"] == "bridge-hub"
        assert "timestamp" in data


class TestEnvelopeIngestion:
    def test_envelope_stored_and_acknowledged(self):
        payload = {
            "from": "manus",
            "to": "bridge",
            "type": "request",
            "payload": {"text": "Hello Bridge"}
        }
        response = client.post("/bridge/envelope", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["envelope"]["from"] == "bridge"
        assert data["envelope"]["to"] == "manus"
        assert data["envelope"]["type"] == "response"
        assert data["envelope"]["payload"]["received"] is True

    def test_envelope_has_messageId_and_threadId(self):
        payload = {
            "from": "manus",
            "to": "bridge",
            "type": "request",
            "payload": {}
        }
        response = client.post("/bridge/envelope", json=payload)
        data = response.json()
        assert "messageId" in data["envelope"]
        assert "threadId" in data["envelope"]
        assert len(data["envelope"]["messageId"]) > 0
        assert len(data["envelope"]["threadId"]) > 0

    def test_envelope_timestamp_is_iso8601(self):
        payload = {
            "from": "manus",
            "to": "bridge",
            "type": "request",
            "payload": {}
        }
        response = client.post("/bridge/envelope", json=payload)
        data = response.json()
        timestamp = data["envelope"]["timestamp"]
        assert "T" in timestamp
        assert "Z" in timestamp or "+" in timestamp


class TestDeduplication:
    def test_duplicate_envelope_by_messageId(self):
        payload = {
            "messageId": "test-dedup-123",
            "from": "manus",
            "to": "bridge",
            "type": "request",
            "payload": {"text": "Hello"}
        }
        
        response1 = client.post("/bridge/envelope", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["envelope"]["payload"]["status"] == "stored"
        
        response2 = client.post("/bridge/envelope", json=payload)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["envelope"]["payload"]["status"] == "duplicate_ignored"

    def test_dedup_in_bridge_run(self):
        payload = {
            "messageId": "test-run-dedup-456",
            "input_text": "Test",
            "mode": "openai_only"
        }
        
        response1 = client.post("/bridge/run", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["ok"] is True
        
        response2 = client.post("/bridge/run", json=payload)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["routed"]["action"] == "duplicate"


class TestBridgeRun:
    def test_bridge_run_openai_only_mock_mode(self):
        payload = {
            "input_text": "Say OK",
            "mode": "openai_only"
        }
        response = client.post("/bridge/run", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "openai" in data["routed"]
        assert data["routed"]["openai"]["provider"] == "openai"
        assert "ok" in data["routed"]["openai"]

    def test_bridge_run_manus_only_mock_mode(self):
        payload = {
            "input_text": "Test",
            "mode": "manus_only"
        }
        response = client.post("/bridge/run", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "manus" in data["routed"]

    def test_bridge_run_openai_then_manus(self):
        payload = {
            "input_text": "Test",
            "mode": "openai_then_manus"
        }
        response = client.post("/bridge/run", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "openai" in data["routed"]
        assert "manus" in data["routed"]

    def test_bridge_run_with_envelope(self):
        envelope_payload = {
            "from": "charjibit",
            "to": "bridge",
            "type": "request",
            "threadId": "thread-xyz",
            "payload": {"text": "Hello from Charjibit"}
        }
        payload = {
            "envelope": envelope_payload,
            "mode": "openai_only"
        }
        response = client.post("/bridge/run", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["envelope"]["from"] == "bridge"
        assert data["envelope"]["threadId"] == envelope_payload["threadId"]

    def test_bridge_run_requires_input(self):
        payload = {
            "mode": "openai_only"
        }
        response = client.post("/bridge/run", json=payload)
        assert response.status_code == 400


class TestCharjibitWebhook:
    def test_charjibit_webhook_converts_to_envelope(self):
        payload = {
            "event_type": "transaction_created",
            "amount": 100,
            "currency": "GEL"
        }
        response = client.post("/webhook/charjibit", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["envelope"]["from"] == "charjibit"
        assert data["envelope"]["to"] == "bridge"
        assert data["envelope"]["type"] == "event"
        assert data["envelope"]["payload"]["event_type"] == "transaction_created"

    def test_charjibit_webhook_dedup_by_event_id(self):
        payload = {
            "event_id": "evt-12345",
            "event_type": "transaction_created",
            "amount": 100
        }
        
        response1 = client.post("/webhook/charjibit", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["ok"] is True
        assert data1["envelope"]["messageId"] == "evt-12345"
        
        response2 = client.post("/webhook/charjibit", json=payload)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["ok"] is False
        assert data2["routed"]["action"] == "duplicate"

    def test_charjibit_webhook_dedup_by_payload_hash(self):
        payload = {
            "event_type": "transaction_created",
            "amount": 100,
            "currency": "GEL"
        }
        
        response1 = client.post("/webhook/charjibit", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["ok"] is True
        messageId1 = data1["envelope"]["messageId"]
        
        response2 = client.post("/webhook/charjibit", json=payload)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["ok"] is False
        assert data2["routed"]["action"] == "duplicate"
        assert data2["envelope"]["payload"]["dedup_key"] == messageId1


class TestManusWebhook:
    def test_manus_webhook_converts_to_envelope(self):
        payload = {
            "event_type": "analysis_complete",
            "result": "OK"
        }
        response = client.post("/webhook/manus", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["envelope"]["from"] == "manus"
        assert data["envelope"]["to"] == "bridge"
        assert data["envelope"]["type"] == "event"

    def test_manus_webhook_dedup_by_payload_hash(self):
        payload = {
            "event_type": "analysis_complete",
            "result": "OK"
        }
        
        response1 = client.post("/webhook/manus", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["ok"] is True
        
        response2 = client.post("/webhook/manus", json=payload)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["ok"] is False
        assert data2["routed"]["action"] == "duplicate"


class TestDebugLog:
    def test_debug_log_returns_events(self):
        client.post("/bridge/envelope", json={
            "from": "manus",
            "to": "bridge",
            "type": "request",
            "payload": {}
        })
        
        response = client.get("/debug/log?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert "items" in data
        assert data["count"] > 0

    def test_debug_log_respects_limit(self):
        for i in range(5):
            client.post("/bridge/envelope", json={
                "from": "manus",
                "to": "bridge",
                "type": "request",
                "payload": {}
            })
        
        response = client.get("/debug/log?limit=2")
        data = response.json()
        assert len(data["items"]) <= 2

    def test_debug_log_includes_stored_at(self):
        client.post("/bridge/envelope", json={
            "from": "manus",
            "to": "bridge",
            "type": "request",
            "payload": {}
        })
        
        response = client.get("/debug/log?limit=1")
        data = response.json()
        assert len(data["items"]) > 0
        for event in data["items"]:
            assert "stored_at" in event


class TestPayloadConsistency:
    def test_all_responses_have_envelope_structure(self):
        payload = {
            "from": "manus",
            "to": "bridge",
            "type": "request",
            "payload": {"text": "Test"}
        }
        response = client.post("/bridge/envelope", json=payload)
        data = response.json()
        envelope = data["envelope"]
        
        required_fields = ["messageId", "threadId", "from", "to", "type", "timestamp", "payload"]
        for field in required_fields:
            assert field in envelope, f"Missing field: {field}"
            assert envelope[field] is not None, f"Field {field} is None"

    def test_payload_never_disappears(self):
        payload = {
            "from": "manus",
            "to": "bridge",
            "type": "request",
            "payload": {"text": "Test"}
        }
        response = client.post("/bridge/envelope", json=payload)
        data = response.json()
        assert isinstance(data["envelope"]["payload"], dict)
        assert data["envelope"]["payload"] is not None


class TestEndToEnd:
    def test_charjibit_event_to_bridge_to_manus(self):
        charjibit_payload = {
            "event_id": "evt-e2e-001",
            "event_type": "transaction_created",
            "amount": 1000,
            "currency": "GEL"
        }
        response1 = client.post("/webhook/charjibit", json=charjibit_payload)
        assert response1.status_code == 200
        charjibit_response = response1.json()
        
        assert charjibit_response["envelope"]["from"] == "charjibit"
        assert charjibit_response["envelope"]["to"] == "bridge"
        assert charjibit_response["envelope"]["messageId"] == "evt-e2e-001"
        
        bridge_run_payload = {
            "envelope": charjibit_response["envelope"],
            "mode": "manus_only"
        }
        response2 = client.post("/bridge/run", json=bridge_run_payload)
        assert response2.status_code == 200
        bridge_response = response2.json()
        
        assert bridge_response["envelope"]["from"] == "bridge"
        assert bridge_response["envelope"]["to"] == "charjibit"
        assert "manus" in bridge_response["routed"]

    def test_full_audit_trail(self):
        client.post("/bridge/envelope", json={
            "from": "manus",
            "to": "bridge",
            "type": "request",
            "payload": {"text": "Test"}
        })
        
        response = client.get("/debug/log")
        data = response.json()
        
        assert data["count"] >= 2
        
        for event in data["items"]:
            assert "stored_at" in event
            assert "kind" in event


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
