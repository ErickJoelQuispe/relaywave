# Importing the models here registers their table metadata on Base.metadata,
# which Alembic's autogenerate reads. Import order is for clarity only.
from app.models.message import Message
from app.models.refresh_token import RefreshToken
from app.models.room import Room
from app.models.room_membership import RoomMembership
from app.models.user import User
from app.models.user_relationship import UserRelationship

__all__ = [
    "Message",
    "RefreshToken",
    "Room",
    "RoomMembership",
    "User",
    "UserRelationship",
]
