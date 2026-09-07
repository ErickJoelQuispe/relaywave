"""Request/response models for the /friends endpoints.

Relationship rows are keyed by the ordered user pair (no relation id is ever
exposed), so every list payload identifies the peer by `user_id` + username
— resolved only for users with whom the caller has that exact relationship
(F1-R7). Message/WS frames keep numeric user ids; usernames appear only in
these relationship-scoped surfaces.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.room import RoomResponse


class FriendRequestSend(BaseModel):
    """Payload for `POST /friends/requests` (F1-R1)."""

    # Length bounds mirror the register contract (UserCreate.username). Any
    # syntactically valid but unknown username is handled uniformly.
    username: str = Field(min_length=1, max_length=50)


class BlockUserRequest(BaseModel):
    """Payload for `POST /friends/blocks` (F1-R6)."""

    user_id: int


class FriendRequestQueued(BaseModel):
    """The uniform, non-committal response to a submitted request (F1-R1).

    Returned whether the username matched an account, matched nothing, or
    the target has blocked the sender — identical status and body so
    response shape never reveals account existence.
    """

    status: Literal["queued"] = "queued"


class PeerSummary(BaseModel):
    """A relationship peer: identity only, never anything else about them."""

    user_id: int
    username: str


class FriendRequestResponse(PeerSummary):
    """A pending request as seen by one side, with the request's age."""

    created_at: datetime


class FriendResponse(BaseModel):
    """A current friendship plus the pair's DM room id (F1-R7)."""

    user_id: int
    username: str
    room_id: int


class BlockedUserResponse(PeerSummary):
    """A user the caller has blocked (resolved from the blocked list)."""


class AcceptFriendRequestResponse(BaseModel):
    """Outcome of `POST /friends/requests/{user_id}/accept` (F1-R4)."""

    peer: PeerSummary
    room: RoomResponse
