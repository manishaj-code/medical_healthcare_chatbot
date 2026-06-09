"""E2E API tests for production agentic chat flows."""
import re

import httpx
import pytest

BASE = "http://localhost:8000/api/v1"


async def _login(client: httpx.AsyncClient) -> str:
    r = await client.post(f"{BASE}/auth/login", json={"email": "john@test.com", "password": "Patient@12345"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["access_token"]


async def _new_conv(client: httpx.AsyncClient, token: str) -> str:
    r = await client.post(
        f"{BASE}/chat/conversations",
        json={"title": "Agentic test", "language": "en"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


async def _say(client: httpx.AsyncClient, token: str, conv_id: str, message: str) -> str:
    r = await client.post(
        f"{BASE}/chat/conversations/{conv_id}/messages",
        json={"message": message},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["reply"]


@pytest.mark.asyncio
async def test_headache_book_cancel_reschedule():
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _login(client)
        conv = await _new_conv(client, token)

        r1 = await _say(client, token, conv, "I have had a headache since yesterday")
        assert "symptom" in r1.lower() or "how long" in r1.lower() or "sorry" in r1.lower()

        r2 = await _say(client, token, conv, "Since yesterday, severity 6 out of 10, front of head, slight dizziness")
        assert "?" in r2 or "detail" in r2.lower() or "other" in r2.lower()

        r3 = await _say(client, token, conv, "Started gradually, poor sleep, no fever")
        assert "doctor" in r3.lower() or "consult" in r3.lower() or "recommend" in r3.lower()

        r4 = await _say(client, token, conv, "Yes")
        assert "available doctors" in r4.lower() or "doctor" in r4.lower()

        r5 = await _say(client, token, conv, "Dr. Patel")
        assert "slot" in r5.lower()
        slot_match = re.search(r"-\s*(?:Today|Tomorrow):\s*(\d{1,2}:\d{2}\s*[AP]M)", r5, re.I)
        assert slot_match, f"No slot found in: {r5}"
        r6 = await _say(client, token, conv, slot_match.group(1))
        assert "confirm" in r6.lower()

        r7 = await _say(client, token, conv, "Yes")
        assert "appointment successfully booked" in r7.lower() or "apt-" in r7.lower()

        r8 = await _say(client, token, conv, "Yes")
        assert "reminder" in r8.lower()

        r9 = await _say(client, token, conv, "I want to cancel my appointment")
        assert "cancel" in r9.lower()

        r10 = await _say(client, token, conv, "Yes")
        assert "cancelled" in r10.lower()

        # Re-book for reschedule test
        conv2 = await _new_conv(client, token)
        r_book_start = await _say(client, token, conv2, "I want to book an appointment")
        assert "doctor" in r_book_start.lower()
        r_book_doc = await _say(client, token, conv2, "Dr. Sharma")
        assert "slot" in r_book_doc.lower(), r_book_doc
        slot2 = re.search(r"-\s*(?:Today|Tomorrow):\s*(\d{1,2}:\d{2}\s*[AP]M)", r_book_doc, re.I)
        assert slot2, r_book_doc
        await _say(client, token, conv2, slot2.group(1))
        await _say(client, token, conv2, "Yes")
        await _say(client, token, conv2, "No")

        r11 = await _say(client, token, conv2, "I need to change my appointment")
        assert "alternative" in r11.lower() or "slot" in r11.lower()

        alt_slot = re.search(r"-\s*(Tomorrow|Today):\s*(\d{1,2}:\d{2}\s*[AP]M)", r11, re.I)
        assert alt_slot, f"No alt slot in: {r11}"
        r12 = await _say(client, token, conv2, f"{alt_slot.group(1)} {alt_slot.group(2)}")
        assert "confirm rescheduling" in r12.lower()

        r13 = await _say(client, token, conv2, "Yes")
        assert "rescheduled" in r13.lower()


@pytest.mark.asyncio
async def test_emergency_and_refill():
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _login(client)

        conv = await _new_conv(client, token)
        r1 = await _say(client, token, conv, "I have chest pain and difficulty breathing")
        assert "emergency" in r1.lower()

        r2 = await _say(client, token, conv, "Yes, pain is severe and going to my left arm")
        assert "emergency" in r2.lower()

        r3 = await _say(client, token, conv, "Yes")
        assert "emergency" in r3.lower() or "waiting" in r3.lower() or "help" in r3.lower()

        conv2 = await _new_conv(client, token)
        r4 = await _say(client, token, conv2, "I need a refill for my blood pressure medicine")
        assert "refill" in r4.lower() or "medication" in r4.lower()

        r5 = await _say(client, token, conv2, "Amlodipine 5mg. Only 2 tablets left.")
        assert "refill" in r5.lower() or "submit" in r5.lower() or "yes" in r5.lower()

        r6 = await _say(client, token, conv2, "Yes")
        assert "refill" in r6.lower()
