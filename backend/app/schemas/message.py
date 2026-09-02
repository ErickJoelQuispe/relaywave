"""WebSocket message envelopes.

Client -> server frames are validated as a Pydantic discriminated union keyed
on `type`, so a malformed frame becomes a `ValidationError` the route can
catch and ignore, instead of a runtime `AttributeError` on a missing field.
Server -> client frames are plain response models sent as `model_dump_json()`.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class AuthEnvelope(BaseModel):
    """The mandatory first frame after the WebSocket handshake.

    The handshake gives browsers no way to set an `Authorization` header, so
    auth travels as the first message instead of a `?token=` query param
    (which would leak a live access token into proxy/access logs).
    """

    type: Literal["auth"]
    token: str


class ChatEnvelope(BaseModel):
    """A chat message the client wants persisted and broadcast."""

    type: Literal["message"]
    content: str = Field(min_length=1, max_length=4000)


class TypingEnvelope(BaseModel):
    """An ephemeral "user is typing" signal. Never persisted."""

    type: Literal["typing"]


ClientEnvelope = Annotated[
    AuthEnvelope | ChatEnvelope | TypingEnvelope,
    Field(discriminator="type"),
]


class MessageBroadcast(BaseModel):
    """Server -> client: a persisted chat message."""

    type: Literal["message"] = "message"
    id: int
    room_id: int
    sender_id: int
    content: str
    created_at: datetime


class TypingBroadcast(BaseModel):
    """Server -> client: someone in the room is typing. Not persisted."""

    type: Literal["typing"] = "typing"
    room_id: int
    user_id: int


class PresenceBroadcast(BaseModel):
    """Server -> client: someone joined or left the room's live connections."""

    type: Literal["presence"] = "presence"
    room_id: int
    event: Literal["join", "leave"]
    user_id: int
