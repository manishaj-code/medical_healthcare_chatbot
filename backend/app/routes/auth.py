from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    PasswordResetMessage,
    ProfileUpdateRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.common import ResponseEnvelope
from app.services.auth_service import (
    login_user,
    refresh_access_token,
    register_user,
    request_password_reset,
    reset_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ResponseEnvelope[UserResponse])
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user = await register_user(db, data)
    return ResponseEnvelope(data=UserResponse.model_validate(user))


@router.post("/login", response_model=ResponseEnvelope[TokenResponse])
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    access, refresh, _ = await login_user(db, data)
    return ResponseEnvelope(data=TokenResponse(access_token=access, refresh_token=refresh))


@router.post("/forgot-password", response_model=ResponseEnvelope[PasswordResetMessage])
async def forgot_password(data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    dev_otp = await request_password_reset(db, data.email)
    return ResponseEnvelope(
        data=PasswordResetMessage(
            message="If an account exists for this email, a reset code has been sent.",
            dev_otp=dev_otp,
        )
    )


@router.post("/reset-password", response_model=ResponseEnvelope[PasswordResetMessage])
async def reset_password_route(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await reset_password(db, data.email, data.otp, data.new_password)
    return ResponseEnvelope(
        data=PasswordResetMessage(message="Password updated successfully. You can sign in now.")
    )


@router.post("/refresh", response_model=ResponseEnvelope[dict])
async def refresh(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    token = await refresh_access_token(db, data.refresh_token)
    return ResponseEnvelope(data={"access_token": token})


@router.get("/me", response_model=ResponseEnvelope[UserResponse])
async def me(user: User = Depends(get_current_user)):
    return ResponseEnvelope(data=UserResponse.model_validate(user))


@router.patch("/me", response_model=ResponseEnvelope[UserResponse])
async def update_me(
    data: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.name:
        user.name = data.name
    await db.flush()
    return ResponseEnvelope(data=UserResponse.model_validate(user))
