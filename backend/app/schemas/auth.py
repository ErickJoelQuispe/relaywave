"""Request/response models for authentication endpoints.

These are deliberately separate from the SQLAlchemy models: the ORM models
describe how rows map to tables, while these describe the wire contract. The
boundary (validation of user input happens here) keeps route handlers thin and
the API surface explicit.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Payload for `POST /auth/register`."""

    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    """Payload for `POST /auth/login`."""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Payload for `POST /auth/refresh` and `POST /auth/logout`."""

    refresh_token: str


class UserResponse(BaseModel):
    """Public representation of a user (never includes the password hash)."""

    # `from_attributes=True` lets FastAPI build this straight from a `User`
    # ORM instance via `response_model`, skipping a manual mapping step.
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    username: str
    created_at: datetime


class TokenResponse(BaseModel):
    """A freshly issued access + refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
