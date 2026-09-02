"""Authentication endpoints: register, login, refresh, logout, and `/me`.

Token lifecycle:
- login / register→login issue an access + refresh pair;
- the refresh token is stored hashed (see `RefreshToken`) and rotated on refresh;
- logout revokes the refresh token so it can no longer mint new access tokens.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.session import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    RefreshRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)

settings = get_settings()

router = APIRouter(prefix="/auth", tags=["auth"])


async def _issue_tokens(user: User, db: AsyncSession) -> TokenResponse:
    """Persist a new refresh token and return a fresh access + refresh pair."""
    jti = str(uuid4())
    refresh_token = create_refresh_token(user.id, jti)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=jti,
            token_hash=hash_token(refresh_token),
            expires_at=datetime.now(UTC)
            + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    access_token = create_access_token(user.id)
    # NOTE: deliberately NO commit here — the caller commits, so that in the
    # refresh path the revocation of the old token and creation of the new one
    # land in the SAME transaction (atomic rotation).
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
async def register(
    payload: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> User:
    """Create a new account.

    The pre-checks give friendly, specific error messages in the common case;
    the `IntegrityError` handler is the safety net for the unavoidable race
    where two requests pass the check and then collide on the unique index.
    """
    if await db.scalar(select(User).where(User.email == payload.email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    if (
        await db.scalar(select(User).where(User.username == payload.username))
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username already taken"
        )

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # The unique constraint won the race against the pre-check above.
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username already registered",
        ) from None
    # Re-read to populate `created_at` (a server default) before returning.
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: UserLogin, db: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse:
    """Authenticate a user and issue a token pair.

    The failure message is deliberately generic — it must not reveal whether
    the email or the password was wrong, or an attacker can enumerate accounts.
    """
    user = await db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    tokens = await _issue_tokens(user, db)
    await db.commit()
    return tokens


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> TokenResponse:
    """Exchange a valid refresh token for a new token pair (rotation).

    Rotation means the presented refresh token is revoked and a NEW one is
    issued, both in one commit. Revoking the old token first and only then
    creating the new one, without an intermediate commit, guarantees the two
    never diverge: either both happen or neither does.
    """
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from None

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type"
        )

    jti = payload.get("jti")
    user_id = int(payload["sub"])

    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    row = result.scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked or invalid",
        )

    # Constant-time compare: a timing side-channel must not reveal how many
    # leading characters of the stored hash match.
    if not secrets.compare_digest(row.token_hash, hash_token(body.refresh_token)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token revoked or invalid",
        )

    # Revoke the presented token BEFORE issuing the replacement. NOTE: no
    # commit here — it must land atomically with the new token below.
    row.revoked_at = datetime.now(UTC)

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    # Future hardening (not implemented here): if the same already-revoked
    # token is presented again, that's reuse — a signal the token may have
    # been stolen — and the entire session family should be revoked.
    tokens = await _issue_tokens(user, db)
    await db.commit()
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: RefreshRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> None:
    """Revoke a refresh token. Idempotent: always returns 204.

    A bad or expired token still returns 204 — there is nothing to revoke, and
    surfacing an error here would give an attacker feedback about which tokens
    were valid.
    """
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError:
        return None

    jti = payload.get("jti")
    if jti is None:
        return None

    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    row = result.scalar_one_or_none()
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await db.commit()
    return None


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Return the authenticated user (proves the access token works)."""
    return current_user
