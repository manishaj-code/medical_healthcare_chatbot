import logging
from dataclasses import dataclass

from app.database import get_settings

logger = logging.getLogger(__name__)


@dataclass
class EmailSendResult:
    sent: bool
    mode: str  # "smtp" | "console"


def smtp_configured() -> bool:
    return bool(get_settings().smtp_host.strip())


def smtp_status() -> dict[str, str | bool]:
    settings = get_settings()
    return {
        "smtp_configured": smtp_configured(),
        "smtp_host": settings.smtp_host or "",
        "smtp_port": settings.smtp_port,
        "smtp_from": settings.smtp_from,
    }


async def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    html_body: str | None = None,
) -> EmailSendResult:
    settings = get_settings()
    if settings.smtp_host:
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = to
        msg.set_content(body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return EmailSendResult(sent=True, mode="smtp")

    log_body = body if not html_body else f"{body}\n\n[HTML template rendered for SMTP delivery]"
    logger.info(
        "Email to %s (SMTP not configured — dev mode)\nSubject: %s\n%s",
        to,
        subject,
        log_body,
    )
    return EmailSendResult(sent=False, mode="console")


async def send_plain_email(to: str, subject: str, body: str) -> EmailSendResult:
    return await send_email(to, subject, body)
