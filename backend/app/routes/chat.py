import zlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_patient_profile
from app.database import get_db
from app.services.flow_state import get_flow
from app.services.symptom_extraction import resolve_detected_symptoms
from app.models import Conversation, Message, Patient
from app.models.enums import MessageRole
from app.schemas.chat import (
    ChatReply,
    ConversationCreate,
    ConversationResponse,
    GuestResumeContext,
    MessageCreate,
    MessageResponse,
    ReportUploadCreate,
    TodayConversationEnsure,
)
from app.schemas.common import ResponseEnvelope

router = APIRouter(prefix="/chat", tags=["chat"])

HEALTH_CHAT_TITLE = "Health Chat"
REPORT_UPLOAD_ACK = (
    "I've received the medical documents you shared. I'm analyzing the clinical data "
    "from your recent reports to better understand your symptoms."
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _later_ts(base: datetime, microseconds: int = 1) -> datetime:
    return base + timedelta(microseconds=microseconds)


async def _next_message_timestamp(db: AsyncSession, conversation_id: UUID) -> datetime:
    """Monotonic per conversation so message order stays stable in the UI."""
    result = await db.execute(
        select(Message.created_at)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    now = _utc_now()
    if last is not None:
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last >= now:
            return _later_ts(last)
    return now


def _local_date_key(created_at, tz_offset_minutes: int) -> str:
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    local = created_at + timedelta(minutes=tz_offset_minutes)
    return local.strftime("%Y-%m-%d")


async def _lock_patient_conversations(db: AsyncSession, patient_id: UUID) -> None:
    lock_id = zlib.crc32(str(patient_id).encode()) & 0x7FFFFFFF
    await db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


async def _merge_into_primary(db: AsyncSession, primary_id: UUID, extra_id: UUID) -> None:
    await db.execute(
        update(Message).where(Message.conversation_id == extra_id).values(conversation_id=primary_id)
    )
    await db.execute(delete(Conversation).where(Conversation.id == extra_id))


async def _cleanup_duplicate_conversations(
    db: AsyncSession, patient: Patient, tz_offset_minutes: int
) -> list[Conversation]:
    await _lock_patient_conversations(db, patient.id)
    result = await db.execute(
        select(Conversation)
        .where(Conversation.patient_id == patient.id)
        .order_by(Conversation.created_at.desc())
    )
    all_convs = list(result.scalars().all())
    by_local_date: dict[str, list[Conversation]] = {}
    for conv in all_convs:
        key = _local_date_key(conv.created_at, tz_offset_minutes)
        by_local_date.setdefault(key, []).append(conv)

    for convs in by_local_date.values():
        if len(convs) <= 1:
            if convs:
                convs[0].title = HEALTH_CHAT_TITLE
            continue
        convs.sort(key=lambda c: c.created_at, reverse=True)
        primary = convs[0]
        for extra in convs[1:]:
            await _merge_into_primary(db, primary.id, extra.id)
        primary.title = HEALTH_CHAT_TITLE

    await db.flush()
    result = await db.execute(
        select(Conversation)
        .where(Conversation.patient_id == patient.id)
        .order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


def _dedupe_by_local_date(conversations: list[Conversation], tz_offset_minutes: int) -> list[Conversation]:
    seen: set[str] = set()
    deduped: list[Conversation] = []
    for conv in conversations:
        key = _local_date_key(conv.created_at, tz_offset_minutes)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(conv)
    return deduped


async def _ensure_today_conversation_impl(
    db: AsyncSession, patient: Patient, data: TodayConversationEnsure
) -> Conversation:
    conversations = await _cleanup_duplicate_conversations(db, patient, data.tz_offset_minutes)
    matches = [c for c in conversations if _local_date_key(c.created_at, data.tz_offset_minutes) == data.local_date]

    if matches:
        primary = matches[0]
        primary.title = HEALTH_CHAT_TITLE
        await db.flush()
        return primary

    conv = Conversation(
        patient_id=patient.id,
        title=HEALTH_CHAT_TITLE,
        language=data.language,
    )
    db.add(conv)
    await db.flush()
    return conv


def _compact_chat_history(history: list[dict]) -> list[dict]:
    compact: list[dict] = []
    for item in history:
        content = (item.get("content") or "").strip()
        if not content:
            continue
        if (
            compact
            and item.get("role") == "user"
            and compact[-1].get("role") == "user"
            and content.lower() == (compact[-1].get("content") or "").strip().lower()
        ):
            continue
        compact.append({"role": item["role"], "content": content})
    return compact


def _message_to_response(message: Message) -> MessageResponse:
    ui = None
    attachment = None
    report_ack = False
    emergency = message.agent_name == "emergency"
    if message.tool_calls_json and isinstance(message.tool_calls_json, dict):
        ui = message.tool_calls_json.get("ui")
        attachment = message.tool_calls_json.get("attachment")
        report_ack = bool(message.tool_calls_json.get("report_ack"))
        emergency = bool(message.tool_calls_json.get("emergency")) or emergency
    return MessageResponse(
        id=message.id,
        role=message.role,
        content=message.content,
        agent_name=message.agent_name,
        created_at=message.created_at,
        ui=ui,
        attachment=attachment,
        report_ack=report_ack,
        emergency=emergency,
    )


@router.post("/conversations", response_model=ResponseEnvelope[ConversationResponse])
async def create_conversation(
    data: ConversationCreate,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    ensure_data = TodayConversationEnsure(
        local_date=data.local_date or now.strftime("%Y-%m-%d"),
        tz_offset_minutes=data.tz_offset_minutes if data.tz_offset_minutes is not None else 0,
        title=HEALTH_CHAT_TITLE,
        language=data.language,
    )
    conv = await _ensure_today_conversation_impl(db, patient, ensure_data)
    return ResponseEnvelope(data=ConversationResponse.model_validate(conv))


@router.get("/conversations", response_model=ResponseEnvelope[list[ConversationResponse]])
async def list_conversations(
    tz_offset_minutes: int = Query(default=0),
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    conversations = await _cleanup_duplicate_conversations(db, patient, tz_offset_minutes)
    deduped = _dedupe_by_local_date(conversations, tz_offset_minutes)
    return ResponseEnvelope(data=[ConversationResponse.model_validate(c) for c in deduped])


@router.post("/conversations/today", response_model=ResponseEnvelope[ConversationResponse])
async def ensure_today_conversation(
    data: TodayConversationEnsure,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    data.title = HEALTH_CHAT_TITLE
    conv = await _ensure_today_conversation_impl(db, patient, data)
    return ResponseEnvelope(data=ConversationResponse.model_validate(conv))


@router.get("/conversations/{conversation_id}/messages", response_model=ResponseEnvelope[list[MessageResponse]])
async def get_messages(
    conversation_id: UUID, patient: Patient = Depends(get_patient_profile), db: AsyncSession = Depends(get_db)
):
    from app.services.appointment_card_service import enrich_stored_appointment_ui

    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
    )
    responses: list[MessageResponse] = []
    for message in result.scalars().all():
        item = _message_to_response(message)
        if item.ui:
            enriched_ui = await enrich_stored_appointment_ui(db, item.ui, patient.user_id)
            if enriched_ui is not item.ui:
                item = item.model_copy(update={"ui": enriched_ui})
        responses.append(item)
    return ResponseEnvelope(data=responses)


@router.post(
    "/conversations/{conversation_id}/resume/complete",
    response_model=ResponseEnvelope[ChatReply],
)
async def complete_guest_resume(
    conversation_id: UUID,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    """Finish a pending guest booking after portal login — shows confirmation card only."""
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    from app.services.appointment_card_service import complete_guest_resume_booking
    from app.services.flow_state import get_flow, set_flow

    flow = await get_flow(conversation_id)
    session = dict(flow.get("session") or {})
    completed = await complete_guest_resume_booking(db, patient, conversation_id, session)
    if not completed:
        raise HTTPException(status_code=400, detail="No pending booking to complete.")

    await set_flow(conversation_id, {"session": session})

    tool_calls_json: dict | None = {"ui": completed["ui"]} if completed.get("ui") else None
    asst_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.assistant,
        content=completed["reply"],
        agent_name=completed["agent"],
        tool_calls_json=tool_calls_json,
        created_at=await _next_message_timestamp(db, conversation_id),
    )
    db.add(asst_msg)
    await db.flush()

    return ResponseEnvelope(
        data=ChatReply(
            reply=completed["reply"],
            agent=completed["agent"],
            emergency=False,
            message_id=asst_msg.id,
            ui=completed.get("ui"),
            detected_symptoms=list(session.get("detected_symptoms") or []),
        )
    )


@router.get(
    "/conversations/{conversation_id}/resume",
    response_model=ResponseEnvelope[GuestResumeContext],
)
async def get_guest_resume_context(
    conversation_id: UUID,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    from app.services.chat_orchestrator import load_patient_resume_context

    ctx = await load_patient_resume_context(conversation_id)
    return ResponseEnvelope(data=GuestResumeContext(**ctx))


@router.get(
    "/conversations/{conversation_id}/detected-symptoms",
    response_model=ResponseEnvelope[list[str]],
)
async def get_detected_symptoms(
    conversation_id: UUID,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
    )
    history = [
        {
            "role": m.role.value if hasattr(m.role, "value") else str(m.role),
            "content": m.content,
        }
        for m in result.scalars().all()
    ]
    flow = await get_flow(conversation_id)
    session = flow.get("session") or {}
    return ResponseEnvelope(data=await resolve_detected_symptoms(session, history))


@router.post("/conversations/{conversation_id}/report-upload", response_model=ResponseEnvelope[list[MessageResponse]])
async def register_report_upload(
    conversation_id: UUID,
    data: ReportUploadCreate,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    attachment_json = {
        "type": "report",
        "report_id": str(data.report_id),
        "filename": data.filename,
    }
    if data.size_bytes is not None:
        attachment_json["size_bytes"] = data.size_bytes

    uploaded_at = await _next_message_timestamp(db, conversation_id)
    user_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.user,
        content=" ",
        tool_calls_json={"attachment": attachment_json},
        created_at=uploaded_at,
    )
    ack_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.assistant,
        content=REPORT_UPLOAD_ACK,
        agent_name="report_agent",
        tool_calls_json={"report_ack": True, "attachment": attachment_json},
        created_at=_later_ts(uploaded_at),
    )
    db.add(user_msg)
    db.add(ack_msg)
    await db.flush()
    return ResponseEnvelope(data=[_message_to_response(user_msg), _message_to_response(ack_msg)])


@router.post("/conversations/{conversation_id}/messages", response_model=ResponseEnvelope[ChatReply])
async def send_message(
    conversation_id: UUID,
    data: MessageCreate,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    attachment_json = None
    if data.report_id:
        attachment_json = {
            "type": "report",
            "report_id": str(data.report_id),
            "filename": data.attachment_filename or "Medical report.pdf",
        }
        if data.attachment_size_bytes is not None:
            attachment_json["size_bytes"] = data.attachment_size_bytes

    user_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.user,
        content=data.message,
        tool_calls_json={"attachment": attachment_json} if attachment_json else None,
        created_at=await _next_message_timestamp(db, conversation_id),
    )
    db.add(user_msg)
    await db.flush()

    hist_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
    )
    history = _compact_chat_history(
        [
            {
                "role": m.role.value if hasattr(m.role, "value") else str(m.role),
                "content": m.content,
            }
            for m in hist_result.scalars().all()
        ]
    )

    report_id = str(data.report_id) if data.report_id else None
    try:
        from app.services.chat_orchestrator import process_patient_message

        reply, agent, emergency, ui, detected_symptoms = await process_patient_message(
            db, conv, patient, data.message, history=history, report_id=report_id
        )
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Chat processing failed. Please try again.")

    tool_calls_json: dict | None = None
    if ui or emergency:
        tool_calls_json = {}
        if ui:
            tool_calls_json["ui"] = ui
        if emergency:
            tool_calls_json["emergency"] = True

    asst_msg = Message(
        conversation_id=conversation_id,
        role=MessageRole.assistant,
        content=reply,
        agent_name=agent,
        tool_calls_json=tool_calls_json,
        created_at=await _next_message_timestamp(db, conversation_id),
    )
    db.add(asst_msg)
    await db.flush()

    return ResponseEnvelope(
        data=ChatReply(
            reply=reply,
            agent=agent,
            emergency=emergency,
            message_id=asst_msg.id,
            ui=ui,
            detected_symptoms=detected_symptoms,
        )
    )
