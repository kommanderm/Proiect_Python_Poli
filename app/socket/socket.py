from flask import request
from flask_socketio import ConnectionRefusedError, SocketIO, emit, join_room, leave_room, rooms

from app import app, validation
from app.db import Message, Permission, Room, User, db
from app.validation import ValidationError

# a message is at most a few KB of JSON; the default would accept 1 MB per packet
socket = SocketIO(app, max_http_buffer_size=64 * 1024)


def channel(room_id):
    return f"room-{room_id}"


def joined_room(data):
    """Return (user, room) for data["room_id"], or raise ValidationError unless the user is a member."""
    user = User.from_session()
    if user is None:
        raise ValidationError("not logged in")
    room = db.session.get(Room, validation.room_id(data))
    if room is None or user.permission(room) != Permission.MEMBER:
        raise ValidationError("you are not a member of this room")
    return user, room


def exit_channels():
    for name in list(rooms()):
        if name != request.sid:
            leave_room(name)


@socket.on_error_default
def on_error(error):
    # whatever is returned here becomes the acknowledgement, so the client is never left waiting
    if isinstance(error, ValidationError):
        return {"ok": False, "error": str(error)}
    db.session.rollback()
    app.logger.exception("socket event %s failed", request.event["message"])
    return {"ok": False, "error": "internal server error"}


@socket.on("connect")
def on_connect(auth=None):
    if User.from_session() is None:
        raise ConnectionRefusedError("not logged in")


@socket.on("enter_room")
def on_enter_room(data=None, *_extra):
    _, room = joined_room(data)
    exit_channels()
    join_room(channel(room.id))
    return {"ok": True}


@socket.on("exit_room")
def on_exit_room(_data=None, *_extra):
    exit_channels()
    return {"ok": True}


@socket.on("send_message")
def on_send_message(data=None, *_extra):
    user, room = joined_room(data)
    message = Message(room_id=room.id, user_id=user.id, content=validation.message_content(data))
    db.session.add(message)
    db.session.commit()
    emit("message", message.to_dict(), to=channel(room.id))
    return {"ok": True}
