import secrets
from datetime import datetime, timezone
from enum import StrEnum

from flask import session
from flask_sqlalchemy import SQLAlchemy

from app import app

db = SQLAlchemy(app)


class Permission(StrEnum):
    NONE = "none"
    MEMBER = "member"


user_in_room = db.Table(
    "user_in_room",
    db.Column("user_id", db.ForeignKey("user.id"), primary_key=True),
    db.Column("room_id", db.ForeignKey("room.id"), primary_key=True),
)


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    # sqlite drops tzinfo on the way in; everything stored is UTC
    return dt.replace(tzinfo=timezone.utc).isoformat()


class User(db.Model):
    # the id is also the login credential, so it is only ever sent to its owner
    id = db.Column(db.String(12), primary_key=True)
    registered_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    display_name = db.Column(db.String(32), nullable=False)
    rooms = db.relationship("Room", secondary=user_in_room, back_populates="users")

    @staticmethod
    def new_id():
        while True:
            user_id = secrets.token_hex(6)
            if db.session.get(User, user_id) is None:
                return user_id

    @staticmethod
    def from_session():
        user_id = session.get("user_id")
        return db.session.get(User, user_id) if user_id else None

    def permission(self, room):
        return Permission.MEMBER if room in self.rooms else Permission.NONE

    def to_dict(self):
        return {
            "id": self.id,
            "display_name": self.display_name,
            "registered_at": iso(self.registered_at),
        }


class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    display_name = db.Column(db.String(32), nullable=False, unique=True)
    users = db.relationship("User", secondary=user_in_room, back_populates="rooms")

    def to_dict(self, user):
        return {
            "id": self.id,
            "display_name": self.display_name,
            "permission": user.permission(self),
        }


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.ForeignKey("room.id"), nullable=False, index=True)
    user_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    user = db.relationship("User", lazy="joined")

    def to_dict(self):
        return {
            "id": self.id,
            "room_id": self.room_id,
            "display_name": self.user.display_name,
            "content": self.content,
            "sent_at": iso(self.sent_at),
        }
