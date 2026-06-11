import logging
import random
import re
import string

from app.database import get_settings
from app.services.cache import get_redis

logger = logging.getLogger(__name__)

OTP_TTL_SECONDS = 600
OTP_PREFIX = "otp:email:"
OTP_RATE_PREFIX = "otp:rate:"
PWD_RESET_OTP_PREFIX = "pwd_reset:otp:"
PWD_RESET_RATE_PREFIX = "pwd_reset:rate:"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


async def store_otp(email: str, otp: str) -> None:
    redis = await get_redis()
    key = OTP_PREFIX + _normalize_email(email)
    await redis.setex(key, OTP_TTL_SECONDS, otp)


async def verify_otp(email: str, otp: str) -> bool:
    redis = await get_redis()
    key = OTP_PREFIX + _normalize_email(email)
    stored = await redis.get(key)
    if not stored or stored != otp.strip():
        return False
    await redis.delete(key)
    return True


async def can_send_otp(email: str) -> bool:
    redis = await get_redis()
    key = OTP_RATE_PREFIX + _normalize_email(email)
    exists = await redis.get(key)
    return exists is None


async def mark_otp_sent(email: str) -> None:
    redis = await get_redis()
    key = OTP_RATE_PREFIX + _normalize_email(email)
    await redis.setex(key, 60, "1")


async def send_otp_email(email: str, otp: str) -> None:
    from app.services.email_templates import format_otp_display, render_otp_verification_email

    settings = get_settings()
    expiry_minutes = OTP_TTL_SECONDS // 60
    otp_display = format_otp_display(otp)
    subject = "Verify Your Email | MedTrust Health"
    plain_body = (
        f"Your MedTrust Health verification code is: {otp_display}\n\n"
        f"This code expires in {expiry_minutes} minutes.\n\n"
        "For your protection, MedTrust Health (MediAI) will never ask for this code "
        "over the phone, email, or chat.\n\n"
        "If you did not request this, please secure your account immediately."
    )
    html_body = render_otp_verification_email(otp, expiry_minutes)

    if settings.smtp_host:
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = email
        msg.set_content(plain_body)
        msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return

    logger.info("OTP for %s: %s (SMTP not configured — dev mode)", email, otp)


async def store_password_reset_otp(email: str, otp: str) -> None:
    redis = await get_redis()
    key = PWD_RESET_OTP_PREFIX + _normalize_email(email)
    await redis.setex(key, OTP_TTL_SECONDS, otp)


async def verify_password_reset_otp(email: str, otp: str) -> bool:
    redis = await get_redis()
    key = PWD_RESET_OTP_PREFIX + _normalize_email(email)
    stored = await redis.get(key)
    if not stored or stored != otp.strip():
        return False
    await redis.delete(key)
    return True


async def can_send_password_reset_otp(email: str) -> bool:
    redis = await get_redis()
    key = PWD_RESET_RATE_PREFIX + _normalize_email(email)
    return await redis.get(key) is None


async def mark_password_reset_otp_sent(email: str) -> None:
    redis = await get_redis()
    key = PWD_RESET_RATE_PREFIX + _normalize_email(email)
    await redis.setex(key, 60, "1")


async def send_password_reset_email(email: str, otp: str) -> None:
    settings = get_settings()
    subject = "Your MediAI password reset code"
    body = (
        f"Your password reset code is: {otp}\n\n"
        f"This code expires in {OTP_TTL_SECONDS // 60} minutes.\n"
        "If you did not request a password reset, you can ignore this email."
    )

    if settings.smtp_host:
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from
        msg["To"] = email
        msg.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return

    logger.info("Password reset OTP for %s: %s (SMTP not configured — dev mode)", email, otp)
