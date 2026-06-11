"""HTML email templates for transactional messages."""
from datetime import datetime
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "email_templates"


def format_otp_display(otp: str) -> str:
    """Format 6-digit OTP as '123 456' for readability."""
    digits = "".join(c for c in otp if c.isdigit())
    if len(digits) == 6:
        return f"{digits[:3]} {digits[3:]}"
    return otp.strip()


def render_otp_verification_email(otp: str, expiry_minutes: int) -> str:
    template_path = _TEMPLATES_DIR / "otp_verification.html"
    html = template_path.read_text(encoding="utf-8")
    return (
        html.replace("{{otp_display}}", format_otp_display(otp))
        .replace("{{expiry_minutes}}", str(expiry_minutes))
        .replace("{{year}}", str(datetime.now().year))
    )
