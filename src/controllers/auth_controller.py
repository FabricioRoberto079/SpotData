from fastapi import APIRouter, Depends, Request

from src.auth import limiter, require_user
from src.interfaces.auth_service import IAuthService
from src.models.user import User
from src.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from src.services.auth_service import get_auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=201,
    summary="Register a user and return its data",
)
@limiter.limit("5/minute")
async def register(
    request: Request,
    payload: RegisterRequest,
    auth_service: IAuthService = Depends(get_auth_service),
):
    return auth_service.register(
        name=payload.name,
        email=payload.email,
        password=payload.password,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and return access_token",
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    payload: LoginRequest,
    auth_service: IAuthService = Depends(get_auth_service),
):
    return auth_service.login(email=payload.email, password=payload.password)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request a password-reset code by email",
)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    auth_service: IAuthService = Depends(get_auth_service),
):
    auth_service.request_password_reset(email=payload.email)
    return {"detail": "If the email is registered, a reset code has been sent."}


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset the password using the emailed code",
)
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    auth_service: IAuthService = Depends(get_auth_service),
):
    auth_service.reset_password(
        email=payload.email,
        code=payload.code,
        new_password=payload.new_password,
    )
    return {"detail": "Password updated. You can now log in with the new password."}


@router.get(
    "/me",
    response_model=UserOut,
    summary="Return the user from the current token",
)
async def me(current_user: User = Depends(require_user)):
    return UserOut(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        role=current_user.role,
    )
