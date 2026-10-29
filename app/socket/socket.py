from flask import request
from flask_socketio import ConnectionRefusedError, SocketIO, emit, join_room, leave_room, rooms

from app import app
from app.db import Message, Permission, Room, User, db

socket = SocketIO(app)

MESSAGE_MAX_LENGTH = 1000


def channel(room_id):
    return f"room-{room_id}"


def joined_room(data):
    """Return (user, room) for data["room_id"]; room is None unless the user is a member."""
    user = User.from_session()
    room_id = data.get("room_id") if isinstance(data, dict) else None
    if user is None or not isinstance(room_id, int):
        return user, None
    room = db.session.get(Room, room_id)
    if room is None or user.permission(room) != Permission.MEMBER:
        return user, None
    return user, room


def exit_channels():
    for name in list(rooms()):
        if name != request.sid:
            leave_room(name)


@socket.on("connect")
def on_connect(auth=None):
    if User.from_session() is None:
        raise ConnectionRefusedError("not logged in")


@socket.on("enter_room")
def on_enter_room(data):
    _, room = joined_room(data)
    if room is None:
        return {"ok": False, "error": "you are not a member of this room"}
    exit_channels()
    join_room(channel(room.id))
    return {"ok": True}


@socket.on("exit_room")
def on_exit_room(_data=None):
    exit_channels()
    return {"ok": True}


@socket.on("send_message")
def on_send_message(data):
    user, room = joined_room(data)
    if room is None:
        return {"ok": False, "error": "you are not a member of this room"}
    content = data.get("content")
    content = content.strip() if isinstance(content, str) else ""
    if not 1 <= len(content) <= MESSAGE_MAX_LENGTH:
        return {"ok": False, "error": f"messages must be 1-{MESSAGE_MAX_LENGTH} characters"}
    message = Message(room_id=room.id, user_id=user.id, content=content)
    db.session.add(message)
    db.session.commit()
    emit("message", message.to_dict(), to=channel(room.id))
    return {"ok": True}
