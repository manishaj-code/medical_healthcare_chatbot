from app.multi_agent.booking_actions import (
    _booking_intent,
    _last_assistant_refill_confirm,
    should_skip_booking_resolution,
)
from app.multi_agent.types import AgentContext


def test_yes_after_refill_offer_is_not_booking_intent():
    history = [
        {"role": "user", "content": "I need a refill for my blood pressure medicine"},
        {
            "role": "assistant",
            "content": (
                "I found **Amlodipine** on your active prescription list. "
                "Would you like me to submit a refill request to your doctor?"
            ),
        },
    ]
    assert _last_assistant_refill_confirm(history)
    assert _booking_intent("Yes", history) is False


def test_skip_booking_while_confirming_refill():
    ctx = AgentContext(
        db=None,
        conversation=None,
        patient=None,
        conv_id="00000000-0000-0000-0000-000000000001",
        text="Yes",
        history=[
            {
                "role": "assistant",
                "content": "Would you like me to submit a refill request to your doctor?",
            }
        ],
        patient_ctx={"name": "John Doe"},
        session={"care_goal": "refill", "awaiting": "confirm_refill", "refill_medication": "Amlodipine"},
    )
    assert should_skip_booking_resolution(ctx) is True
