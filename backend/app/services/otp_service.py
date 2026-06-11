import random
import string

from app.services.cache import get_redis
from app.services.email_service import EmailSendResult, send_email
from app.services.email_templates import render_otp_verification_email

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


async def send_otp_email(email: str, otp: str) -> EmailSendResult:
    expiry_minutes = OTP_TTL_SECONDS // 60
    subject = "Your MediAI verification code"
    body = (
        f"Your MediAI verification code is: {otp}\n\n"
        f"This code expires in {expiry_minutes} minutes.\n"
        "If you did not request this, you can ignore this email."
    )
    html_body = render_otp_verification_email(otp, expiry_minutes)
    return await send_email(email, subject, body, html_body=html_body)


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


async def send_password_reset_email(email: str, otp: str) -> EmailSendResult:
    expiry_minutes = OTP_TTL_SECONDS // 60
    subject = "Your MediAI password reset code"
    body = (
        f"Your password reset code is: {otp}\n\n"
        f"This code expires in {expiry_minutes} minutes.\n"
        "If you did not request a password reset, you can ignore this email."
    )
    html_body = render_otp_verification_email(otp, expiry_minutes)
    return await send_email(email, subject, body, html_body=html_body)
