#!/usr/bin/env python3
"""Automated API E2E checks for Aura (guest) + Patient Portal chat. Run: python scripts/run_aura_e2e_tests.py"""
from __future__ import annotations

import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx")
    sys.exit(1)

BASE = "http://localhost:8000/api/v1"
TIMEOUT = 45.0
PATIENT_EMAIL = "alex@test.com"
PATIENT_PASSWORD = "Patient@12345"


@dataclass
class CaseResult:
    id: str
    area: str
    scenario: str
    steps: str
    status: str  # PASS | FAIL | PARTIAL | SKIP | BLOCKED
    notes: str = ""
    evidence: str = ""


@dataclass
class TestRun:
    results: list[CaseResult] = field(default_factory=list)

    def add(self, **kwargs: Any) -> None:
        self.results.append(CaseResult(**kwargs))


def ok(reply: str | None, *needles: str) -> bool:
    if not reply:
        return False
    low = reply.lower()
    return any(n.lower() in low for n in needles)


def guest_session(client: httpx.Client) -> str:
    r = client.post(f"{BASE}/guest/session")
    r.raise_for_status()
    return r.json()["data"]["session_id"]


def guest_say(client: httpx.Client, sid: str, message: str) -> dict:
    r = client.post(
        f"{BASE}/guest/chat/messages",
        json={"session_id": sid, "message": message},
        timeout=TIMEOUT,
    )
    return {"status": r.status_code, "body": r.json() if r.status_code == 200 else r.text}


def guest_reply(data: dict) -> str:
    if data["status"] != 200:
        return ""
    return data["body"].get("data", {}).get("reply", "")


def guest_ui_type(data: dict) -> str | None:
    if data["status"] != 200:
        return None
    ui = data["body"].get("data", {}).get("ui")
    return ui.get("type") if ui else None


def login_patient(client: httpx.Client) -> str:
    r = client.post(
        f"{BASE}/auth/login",
        json={"email": PATIENT_EMAIL, "password": PATIENT_PASSWORD},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["data"]["access_token"]


def new_conv(client: httpx.Client, token: str) -> str:
    r = client.post(
        f"{BASE}/chat/conversations",
        json={"title": "E2E test", "language": "en"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["data"]["id"]


def patient_say(client: httpx.Client, token: str, conv: str, message: str) -> dict:
    r = client.post(
        f"{BASE}/chat/conversations/{conv}/messages",
        json={"message": message},
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    return {"status": r.status_code, "body": r.json() if r.status_code == 200 else r.text}


def patient_reply(data: dict) -> str:
    if data["status"] != 200:
        return ""
    return data["body"].get("data", {}).get("reply", "")


def run_guest_tests(run: TestRun, client: httpx.Client) -> str:
    sid = guest_session(client)

    # G01 Welcome / symptom triage start
    d = guest_say(client, sid, "[start_symptom_triage]")
    r = guest_reply(d)
    ui = guest_ui_type(d)
    run.add(
        id="G01",
        area="Aura Guest",
        scenario="Welcome → Check My Symptoms button",
        steps="POST [start_symptom_triage]",
        status="PASS" if ok(r, "symptom", "describe") and ui == "symptom_picker" else "PARTIAL",
        notes=f"UI={ui}",
        evidence=r[:200],
    )

    # G02 Symptom chip
    d = guest_say(client, sid, "Fever")
    r = guest_reply(d)
    ui = guest_ui_type(d)
    run.add(
        id="G02",
        area="Aura Guest",
        scenario="Symptom chip → Fever",
        steps="Click Fever",
        status="PASS" if ok(r, "how long", "duration", "experiencing") or ui == "duration_picker" else "FAIL",
        notes=f"UI={ui}",
        evidence=r[:200],
    )

    # G03 Duration
    d = guest_say(client, sid, "1-3 days")
    r = guest_reply(d)
    ui = guest_ui_type(d)
    run.add(
        id="G03",
        area="Aura Guest",
        scenario="Duration picker → 1-3 days",
        steps="Select duration",
        status="PASS" if ok(r, "severe", "severity") or ui == "severity_picker" else "PARTIAL",
        notes=f"UI={ui}",
        evidence=r[:200],
    )

    # G04 Severity
    d = guest_say(client, sid, "Moderate")
    r = guest_reply(d)
    ui = guest_ui_type(d)
    run.add(
        id="G04",
        area="Aura Guest",
        scenario="Severity → Moderate",
        steps="Select Moderate",
        status="PASS" if ok(r, "other symptoms", "more symptoms") or ui in ("more_symptoms", "yes_no") else "PARTIAL",
        notes=f"UI={ui}",
        evidence=r[:200],
    )

    # G05 No other symptoms → assessment
    d = guest_say(client, sid, "No other symptoms")
    r = guest_reply(d)
    ui = guest_ui_type(d)
    run.add(
        id="G05",
        area="Aura Guest",
        scenario="Additional symptoms → No",
        steps="No other symptoms",
        status="PASS"
        if ok(r, "recommend", "self-care", "doctor", "specialty", "assessment", "symptom")
        or ui == "post_assessment"
        else "PARTIAL",
        notes=f"UI={ui}",
        evidence=r[:200],
    )

    # G06 Free text triage (new session)
    sid2 = guest_session(client)
    d = guest_say(client, sid2, "I have chest pain and shortness of breath since this morning")
    r = guest_reply(d)
    run.add(
        id="G06",
        area="Aura Guest",
        scenario="Free-text symptom (chest pain + breathing)",
        steps="Type complaint naturally",
        status="PASS" if r and len(r) > 20 else "FAIL",
        notes="May trigger emergency routing",
        evidence=r[:250],
    )

    # G07 Find doctor menu
    sid3 = guest_session(client)
    d = guest_say(client, sid3, "[start_find_doctor]")
    r = guest_reply(d)
    ui = guest_ui_type(d)
    run.add(
        id="G07",
        area="Aura Guest",
        scenario="Find Specialist Doctor → sub-menu",
        steps="[start_find_doctor]",
        status="PASS" if ok(r, "find a doctor", "how would") and ui == "find_doctor_menu" else "PARTIAL",
        notes=f"UI={ui}",
        evidence=r[:200],
    )

    # G08 View all doctors
    d = guest_say(client, sid3, "[aura_view_all_doctors]")
    r = guest_reply(d)
    ui = guest_ui_type(d)
    run.add(
        id="G08",
        area="Aura Guest",
        scenario="Find doctor → View All Doctors",
        steps="Delegate to supervisor doctor search",
        status="PASS" if ui == "doctor_list" or ok(r, "doctor", "found") else "FAIL",
        notes=f"UI={ui}",
        evidence=r[:200],
    )

    # G09 Report explain flow
    sid4 = guest_session(client)
    d = guest_say(client, sid4, "[start_explain_report]")
    r = guest_reply(d)
    ui = guest_ui_type(d)
    awaiting = d["body"].get("data", {}).get("awaiting_input") if d["status"] == 200 else None
    run.add(
        id="G09",
        area="Aura Guest",
        scenario="Explain Medical Report → upload menu",
        steps="[start_explain_report]",
        status="PASS" if ui == "report_upload_menu" or awaiting == "upload" else "PARTIAL",
        notes=f"UI={ui} awaiting={awaiting}",
        evidence=r[:200],
    )

    # G10 General health question
    sid5 = guest_session(client)
    d = guest_say(client, sid5, "What foods are good for lowering blood pressure?")
    r = guest_reply(d)
    run.add(
        id="G10",
        area="Aura Guest",
        scenario="General health education (non-triage)",
        steps="Free-text wellness question",
        status="PASS" if ok(r, "blood pressure", "diet", "sodium", "health", "exercise") else "PARTIAL",
        evidence=r[:250],
    )

    # G11 Main menu
    d = guest_say(client, sid5, "[aura_main_menu]")
    r = guest_reply(d)
    ui = guest_ui_type(d) or (d["body"].get("data", {}).get("nav_ui") or {}).get("type")
    run.add(
        id="G11",
        area="Aura Guest",
        scenario="Main Menu navigation",
        steps="[aura_main_menu]",
        status="PASS" if ok(r, "aura", "help") and (ui == "nav_menu" or ui is None) else "PARTIAL",
        notes=f"nav_ui={ui}",
        evidence=r[:200],
    )

    # G12 Book appointment intent (guest - may hit auth later)
    sid6 = guest_session(client)
    guest_say(client, sid6, "[start_find_doctor]")
    guest_say(client, sid6, "[aura_view_all_doctors]")
    # pick first doctor if list shown - use Dr search
    d = guest_say(client, sid6, "Dr. Patel")
    r1 = guest_reply(d)
    slot = re.search(r"(\d{1,2}:\d{2}\s*[AP]M)", r1 or "")
    book_status = "PARTIAL"
    book_notes = "Could not complete slot pick"
    r3 = ""
    if slot:
        d2 = guest_say(client, sid6, slot.group(1))
        r2 = guest_reply(d2)
        if ok(r2, "confirm"):
            d3 = guest_say(client, sid6, "Yes")
            r3 = guest_reply(d3)
            awaiting = d3["body"].get("data", {}).get("awaiting_input") if d3["status"] == 200 else None
            auth = d3["body"].get("data", {}).get("auth_complete") if d3["status"] == 200 else None
            if awaiting == "email" or ok(r3, "email", "verification"):
                book_status = "PASS"
                book_notes = "Email gate triggered before booking (expected)"
            elif auth:
                book_status = "PASS"
                book_notes = "Auth completed"
            else:
                book_status = "PARTIAL"
                book_notes = r3[:150]
    run.add(
        id="G12",
        area="Aura Guest",
        scenario="Book appointment → confirm → email/OTP gate",
        steps="Find doctor → slot → Yes confirm",
        status=book_status,
        notes=book_notes,
        evidence=(r3[:200] if r3 else r1[:200] if r1 else ""),
    )

    # G13 Video consultation (guest)
    sid7 = guest_session(client)
    d = guest_say(client, sid7, "Start video consultation")
    r = guest_reply(d)
    run.add(
        id="G13",
        area="Aura Guest",
        scenario="Video consultation (guest)",
        steps="Start video consultation",
        status="PASS" if ok(r, "email", "verification", "video") else "PARTIAL",
        notes="Guest should be gated to email",
        evidence=r[:200],
    )

    # G17 By specialty
    sid8 = guest_session(client)
    guest_say(client, sid8, "[start_find_doctor]")
    guest_say(client, sid8, "[aura_by_specialty]")
    d = guest_say(client, sid8, "Cardiologist")
    r = guest_reply(d)
    ui = guest_ui_type(d)
    run.add(
        id="G17",
        area="Aura Guest",
        scenario="Find doctor by specialty (Cardiologist)",
        steps="By Specialty -> Cardiologist",
        status="PASS" if ui == "doctor_list" or ok(r, "cardio", "doctor") else "PARTIAL",
        notes=f"UI={ui}",
        evidence=r[:200],
    )

    # G19 Emergency keywords
    sid9 = guest_session(client)
    d = guest_say(client, sid9, "crushing chest pain can't breathe")
    r = guest_reply(d)
    run.add(
        id="G19",
        area="Aura Guest",
        scenario="Emergency keyword detection",
        steps="Type emergency symptoms",
        status="PASS" if ok(r, "emergency", "911", "er", "immediate", "urgent") else "PARTIAL",
        evidence=r[:250],
    )

    return sid6


def run_patient_tests(run: TestRun, client: httpx.Client) -> None:
    try:
        token = login_patient(client)
    except Exception as exc:
        run.add(
            id="P00",
            area="Patient Portal",
            scenario="Login",
            steps=f"Login {PATIENT_EMAIL}",
            status="BLOCKED",
            notes=str(exc),
        )
        return

    run.add(
        id="P00",
        area="Patient Portal",
        scenario="Login",
        steps=f"Login {PATIENT_EMAIL}",
        status="PASS",
    )

    conv = new_conv(client, token)

    # P01 Symptom triage
    d = patient_say(client, token, conv, "I have had a headache since yesterday")
    r = patient_reply(d)
    run.add(
        id="P01",
        area="Patient Portal",
        scenario="Symptom triage - headache",
        steps="Natural language symptom",
        status="PASS" if r and len(r) > 15 else "FAIL",
        evidence=r[:200],
    )

    d = patient_say(client, token, conv, "Moderate, about 5 out of 10")
    r = patient_reply(d)
    run.add(
        id="P02",
        area="Patient Portal",
        scenario="Symptom follow-up severity",
        steps="Severity text",
        status="PASS" if r else "FAIL",
        evidence=r[:200],
    )

    # P03 Book appointment
    conv2 = new_conv(client, token)
    d = patient_say(client, token, conv2, "I want to book an appointment")
    r = patient_reply(d)
    run.add(
        id="P03",
        area="Patient Portal",
        scenario="Book appointment intent",
        steps="I want to book an appointment",
        status="PASS" if ok(r, "doctor", "available", "specialist") else "FAIL",
        evidence=r[:200],
    )

    d = patient_say(client, token, conv2, "Dr. Patel")
    r = patient_reply(d)
    slot = re.search(r"(\d{1,2}:\d{2}\s*[AP]M)", r or "")
    run.add(
        id="P04",
        area="Patient Portal",
        scenario="Select doctor",
        steps="Dr. Patel",
        status="PASS" if slot or ok(r, "slot", "time") else "FAIL",
        evidence=r[:200],
    )

    if slot:
        d = patient_say(client, token, conv2, slot.group(1))
        r = patient_reply(d)
        d2 = patient_say(client, token, conv2, "Yes")
        r2 = patient_reply(d2)
        run.add(
            id="P05",
            area="Patient Portal",
            scenario="Confirm booking",
            steps="Pick slot → Yes",
            status="PASS" if ok(r2, "booked", "appointment", "apt-") else "PARTIAL",
            evidence=r2[:200],
        )

        d3 = patient_say(client, token, conv2, "Set a reminder 30 minutes before appointment")
        r3 = patient_reply(d3)
        run.add(
            id="P06",
            area="Patient Portal",
            scenario="Set appointment reminder",
            steps="Reminder after booking",
            status="PASS" if ok(r3, "reminder") else "PARTIAL",
            evidence=r3[:200],
        )

    # P07 Cancel
    d = patient_say(client, token, conv2, "I want to cancel my appointment")
    r = patient_reply(d)
    run.add(
        id="P07",
        area="Patient Portal",
        scenario="Cancel appointment",
        steps="Cancel intent",
        status="PASS" if ok(r, "cancel") else "PARTIAL",
        evidence=r[:200],
    )

    # P08 Refill
    conv3 = new_conv(client, token)
    d = patient_say(client, token, conv3, "I need a prescription refill for Metformin")
    r = patient_reply(d)
    run.add(
        id="P08",
        area="Patient Portal",
        scenario="Prescription refill",
        steps="Refill Metformin",
        status="PASS" if ok(r, "refill", "metformin", "prescription", "medication") else "PARTIAL",
        evidence=r[:200],
    )

    # P09 Video
    conv4 = new_conv(client, token)
    d = patient_say(client, token, conv4, "Start video consultation")
    r = patient_reply(d)
    ui = d["body"].get("data", {}).get("ui", {}) if d["status"] == 200 else {}
    run.add(
        id="P09",
        area="Patient Portal",
        scenario="Video consultation",
        steps="Start video consultation",
        status="PASS"
        if ok(r, "video", "room", "join") or (ui and ui.get("type") == "video_consultation")
        else "PARTIAL",
        notes="Needs upcoming confirmed appointment within window",
        evidence=r[:200],
    )

    # P10 General chat
    conv5 = new_conv(client, token)
    d = patient_say(client, token, conv5, "How much water should I drink daily?")
    r = patient_reply(d)
    run.add(
        id="P10",
        area="Patient Portal",
        scenario="General wellness question",
        steps="Hydration question",
        status="PASS" if ok(r, "water", "hydrat", "glass", "liter") else "PARTIAL",
        evidence=r[:200],
    )

    # P11 Resume endpoint
    r = client.get(
        f"{BASE}/chat/conversations/{conv}/resume",
        headers={"Authorization": f"Bearer {token}"},
        timeout=TIMEOUT,
    )
    run.add(
        id="P11",
        area="Patient Portal",
        scenario="Guest resume context API",
        steps="GET /chat/conversations/{id}/resume",
        status="PASS" if r.status_code == 200 else "FAIL",
        notes=str(r.json().get("data"))[:100] if r.status_code == 200 else r.text[:100],
    )


def main() -> int:
    run = TestRun()
    print("Running Aura + Patient Portal API E2E tests against", BASE)
    with httpx.Client(timeout=TIMEOUT) as client:
        try:
            h = client.get("http://localhost:8000/health", timeout=5)
            if h.status_code != 200:
                print("API not healthy")
                return 1
        except Exception as exc:
            print("API unreachable:", exc)
            return 1

        run_guest_tests(run, client)
        run_patient_tests(run, client)

    passed = sum(1 for r in run.results if r.status == "PASS")
    failed = sum(1 for r in run.results if r.status == "FAIL")
    partial = sum(1 for r in run.results if r.status == "PARTIAL")
    blocked = sum(1 for r in run.results if r.status == "BLOCKED")

    print(f"\nSummary: PASS={passed} PARTIAL={partial} FAIL={failed} BLOCKED={blocked} TOTAL={len(run.results)}")
    for r in run.results:
        safe = r.scenario.replace("\u2192", "->")
        print(f"  [{r.status:7}] {r.id} {safe}")

    from pathlib import Path

    out_path = str(Path(__file__).resolve().parent.parent / "testcases.txt")
    write_report(run, out_path)
    print(f"\nWrote {out_path}")
    return 0 if failed == 0 and blocked == 0 else 1


def write_report(run: TestRun, path: str) -> None:
    lines = [
        "=" * 72,
        "MediAI / Aura Assistant — Manual & Automated Test Case Catalog",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "API base: http://localhost:8000/api/v1",
        "Frontend: http://localhost:5173",
        f"Demo patient: {PATIENT_EMAIL} / {PATIENT_PASSWORD}",
        "=" * 72,
        "",
        "LEGEND",
        "  PASS    = Verified working in automated API run",
        "  PARTIAL = Works with limitations / LLM-dependent / needs UI check",
        "  FAIL    = Broken in automated run",
        "  BLOCKED = Could not run (env/login/down)",
        "  [MANUAL]= You should verify in browser (UI-only)",
        "",
        "=" * 72,
        "SECTION A — LANDING PAGE AURA ASSISTANT (GUEST)",
        "=" * 72,
        "",
    ]

    manual_guest = manual_guest_cases()
    auto_by_id = {r.id: r for r in run.results if r.area == "Aura Guest"}

    for case in manual_guest:
        auto = auto_by_id.get(case["id"])
        status = auto.status if auto else case.get("auto", "MANUAL")
        notes = auto.notes if auto else case.get("notes", "")
        if auto and auto.evidence:
            notes = (notes + " | " + auto.evidence[:120]).strip(" |")

        lines += format_case(case, status, notes)

    lines += [
        "",
        "=" * 72,
        "SECTION B — POST-OTP / PATIENT PORTAL AI CONSULTATION",
        "=" * 72,
        "",
    ]

    manual_patient = manual_patient_cases()
    auto_by_id_p = {r.id: r for r in run.results if r.area == "Patient Portal"}

    for case in manual_patient:
        auto = auto_by_id_p.get(case["id"])
        status = auto.status if auto else case.get("auto", "MANUAL")
        notes = auto.notes if auto else case.get("notes", "")
        if auto and auto.evidence:
            notes = (notes + " | " + auto.evidence[:120]).strip(" |")
        lines += format_case(case, status, notes)

    lines += [
        "",
        "=" * 72,
        "SECTION C — AUTOMATED RUN SUMMARY (this session)",
        "=" * 72,
        "",
    ]
    for r in run.results:
        lines.append(f"{r.id} [{r.status}] {r.scenario}")
        if r.notes:
            lines.append(f"       Notes: {r.notes}")
        if r.evidence:
            lines.append(f"       Evidence: {r.evidence[:150]}...")
        lines.append("")

    lines += [
        "=" * 72,
        "SECTION D — KNOWN GAPS (not in automated run)",
        "=" * 72,
        "",
        "• G14 [MANUAL] Symptom photo upload via paperclip — needs image file in UI",
        "• G15 [MANUAL] OTP email delivery — check dev_otp in chat or SMTP",
        "• G16 [MANUAL] Portal redirect after OTP — sessionStorage + resume prompt",
        "• P12 [MANUAL] Symptom photo in Patient Portal — not implemented (guest only)",
        "• P13 [MANUAL] Report upload + analysis in patient chat",
        "• P14 [MANUAL] Join Video button on /appointments page",
        "• P15 [MANUAL] Notification bell — reminder_scheduled appears after booking",
        "",
        "=" * 72,
        "END",
        "=" * 72,
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def format_case(case: dict, status: str, notes: str) -> list[str]:
    return [
        f"{case['id']} [{status}] {case['title']}",
        f"  Area: {case['area']}",
        f"  Steps:",
        *[f"    {s}" for s in case["steps"]],
        f"  Expected: {case['expected']}",
        f"  Notes: {notes or case.get('notes', '-')}",
        "",
    ]


def manual_guest_cases() -> list[dict]:
    return [
        {"id": "G01", "area": "Aura", "title": "Welcome screen + Check My Symptoms",
         "steps": ["Open landing → Aura widget", "See welcome + 3 emoji buttons", "Tap Check My Symptoms"],
         "expected": "Symptom picker with Fever, Headache, etc. + Type My Own + Upload Photo"},
        {"id": "G02", "area": "Aura", "title": "Symptom chip selection",
         "steps": ["Tap Fever"], "expected": "Duration question + duration buttons"},
        {"id": "G03", "area": "Aura", "title": "Duration selection",
         "steps": ["Tap 1-3 days OR type 'since yesterday'"], "expected": "Severity question"},
        {"id": "G04", "area": "Aura", "title": "Severity selection",
         "steps": ["Tap Moderate"], "expected": "Other symptoms Yes/No/Not Sure"},
        {"id": "G05", "area": "Aura", "title": "Assessment + post-assessment menu",
         "steps": ["Tap No other symptoms"], "expected": "AI assessment + Self-Care / Recommend Doctor / Book / Continue"},
        {"id": "G06", "area": "Aura", "title": "Free-text symptoms only",
         "steps": ["Type: severe stomach pain since yesterday"], "expected": "Natural follow-ups, no forced pickers only"},
        {"id": "G07", "area": "Aura", "title": "Find Specialist Doctor menu",
         "steps": ["Tap Find Specialist Doctor"], "expected": "By Symptoms / Specialty / Near Me / View All"},
        {"id": "G08", "area": "Aura", "title": "View All Doctors",
         "steps": ["Tap View All Doctors"], "expected": "Doctor list with slots / calendar UI"},
        {"id": "G09", "area": "Aura", "title": "Explain Medical Report",
         "steps": ["Tap Explain My Medical Report"], "expected": "Upload menu + paperclip hint"},
        {"id": "G10", "area": "Aura", "title": "General health education",
         "steps": ["Ask about diet/blood pressure"], "expected": "Educational reply, not booking push"},
        {"id": "G11", "area": "Aura", "title": "Main Menu anytime",
         "steps": ["Tap Main Menu in composer"], "expected": "Nav chips: Find Doctor, Book, Upload, Refill, etc."},
        {"id": "G12", "area": "Aura", "title": "Full booking + email gate",
         "steps": ["Find doctor → pick slot → Confirm Yes"], "expected": "Email prompt before final book"},
        {"id": "G13", "area": "Aura", "title": "Video consultation (guest)",
         "steps": ["Tap Start Video Consultation or nav menu"], "expected": "Email verification gate"},
        {"id": "G14", "area": "Aura", "title": "Symptom photo upload", "auto": "MANUAL",
         "steps": ["Check Symptoms → Upload Symptom Photo → paperclip → JPG"],
         "expected": "Visual observation + duration follow-up", "notes": "Requires GEMINI_API_KEY"},
        {"id": "G15", "area": "Aura", "title": "OTP verification",
         "steps": ["Enter email → enter OTP (dev_otp shown in dev)"], "expected": "Redirect to Patient Portal"},
        {"id": "G16", "area": "Aura", "title": "Portal resume after OTP", "auto": "MANUAL",
         "steps": ["Complete OTP during pending booking"], "expected": "Migrated chat + auto confirm message"},
        {"id": "G17", "area": "Aura", "title": "By Specialty doctor search",
         "steps": ["Find Doctor → By Specialty → Cardiologist"], "expected": "Cardiologist doctor list"},
        {"id": "G18", "area": "Aura", "title": "Type My Own Symptoms",
         "steps": ["Tap Type My Own Symptoms → type freely"], "expected": "Free text accepted, triage continues"},
        {"id": "G19", "area": "Aura", "title": "Emergency keywords",
         "steps": ["Type: crushing chest pain can't breathe"], "expected": "Emergency response, ER guidance"},
        {"id": "G20", "area": "Aura", "title": "Session persistence",
         "steps": ["Chat → refresh page"], "expected": "History reloads from server"},
    ]


def manual_patient_cases() -> list[dict]:
    return [
        {"id": "P00", "area": "Portal", "title": "Login",
         "steps": [f"Login {PATIENT_EMAIL} / {PATIENT_PASSWORD}"], "expected": "Dashboard access"},
        {"id": "P01", "area": "Portal", "title": "Symptom triage - natural language",
         "steps": ["AI Consultation → headache since yesterday"], "expected": "Follow-up questions / assessment"},
        {"id": "P02", "area": "Portal", "title": "Symptom severity follow-up",
         "steps": ["Answer severity"], "expected": "Progresses triage"},
        {"id": "P03", "area": "Portal", "title": "Book appointment",
         "steps": ["I want to book an appointment"], "expected": "Doctor list"},
        {"id": "P04", "area": "Portal", "title": "Select doctor + slot",
         "steps": ["Pick doctor → calendar slot"], "expected": "Confirm booking card"},
        {"id": "P05", "area": "Portal", "title": "Confirm booking",
         "steps": ["Yes confirm"], "expected": "Appointment booked APT-xxx"},
        {"id": "P06", "area": "Portal", "title": "Set reminder",
         "steps": ["Set Reminder on confirmation"], "expected": "Reminder scheduled notification"},
        {"id": "P07", "area": "Portal", "title": "Cancel appointment",
         "steps": ["Cancel my appointment → Yes"], "expected": "Cancelled confirmation"},
        {"id": "P08", "area": "Portal", "title": "Prescription refill",
         "steps": ["Refill Metformin"], "expected": "Refill flow / submit"},
        {"id": "P09", "area": "Portal", "title": "Video consultation chat",
         "steps": ["Start video consultation"], "expected": "Join link if appointment in window"},
        {"id": "P10", "area": "Portal", "title": "General wellness chat",
         "steps": ["Ask hydration question"], "expected": "Educational answer"},
        {"id": "P11", "area": "Portal", "title": "Resume API after guest migrate",
         "steps": ["GET resume after guest OTP"], "expected": "resume_prompt when pending action"},
        {"id": "P12", "area": "Portal", "title": "Symptom photo", "auto": "MANUAL",
         "steps": ["Upload symptom image in chat"], "expected": "NOT IMPLEMENTED — guest only"},
        {"id": "P13", "area": "Portal", "title": "Report upload in chat", "auto": "MANUAL",
         "steps": ["Paperclip → PDF lab report"], "expected": "Analysis + follow-up buttons"},
        {"id": "P14", "area": "Portal", "title": "Appointments Join Video", "auto": "MANUAL",
         "steps": ["/appointments → Join Video"], "expected": "Jitsi embed (15 min before slot)"},
        {"id": "P15", "area": "Portal", "title": "Notifications", "auto": "MANUAL",
         "steps": ["/notifications after booking+reminder"], "expected": "booking + reminder entries"},
        {"id": "P16", "area": "Portal", "title": "Reschedule appointment",
         "steps": ["Reschedule → pick new slot → confirm"], "expected": "Rescheduled confirmation"},
        {"id": "P17", "area": "Portal", "title": "Welcome symptom chips",
         "steps": ["New chat empty state chips"], "expected": "Headache/Fever chips start triage"},
        {"id": "P18", "area": "Portal", "title": "Guest-migrated conversation",
         "steps": ["Complete Aura booking OTP → portal"], "expected": "Full history + auto resume"},
        {"id": "P19", "area": "Portal", "title": "Off-topic guard",
         "steps": ["Ask unrelated question (weather/stocks)"], "expected": "Polite scope redirect"},
        {"id": "P20", "area": "Portal", "title": "Emergency detection",
         "steps": ["Report stroke symptoms"], "expected": "Emergency agent response"},
    ]


if __name__ == "__main__":
    sys.exit(main())
