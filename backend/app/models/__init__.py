# Importing the models here registers their table metadata on Base.metadata,
# which Alembic's autogenerate reads. Import order is for clarity only.
from app.models.message import Message
from app.models.room import Room
from app.models.room_membership import RoomMembership
from app.models.user import User

__all__ = ["Message", "Room", "RoomMembership", "User"]
