"""Reproduce guest chat 500 for symptom messages."""
import pytest


@pytest.mark.asyncio
async def test_guest_symptom_message(client):
    session = (await client.post("/api/v1/guest/session")).json()["data"]["session_id"]
    resp = await client.post(
        "/api/v1/guest/chat/messages",
        json={"session_id": session, "message": "I have fever and headache"},
    )
    assert resp.status_code == 200, resp.text
