from functools import wraps

from flask import Blueprint, abort, jsonify, request, session
from werkzeug.exceptions import HTTPException

from app.db import Message, Permission, Room, User, db
from app.socket import socket

api = Blueprint("api", __name__, url_prefix="/api")

NAME_MAX_LENGTH = 32
HISTORY_LIMIT = 100


@api.errorhandler(HTTPException)
def json_error(error):
    return jsonify(error=error.description), error.code


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = User.from_session()
        if user is None:
            abort(401, "not logged in")
        return view(user, *args, **kwargs)

    return wrapper


def json_field(name):
    data = request.get_json(silent=True)
    value = data.get(name) if isinstance(data, dict) else None
    return value.strip() if isinstance(value, str) else ""


def display_name_field():
    name = json_field("display_name")
    if not 1 <= len(name) <= NAME_MAX_LENGTH:
        abort(400, f"display name must be 1-{NAME_MAX_LENGTH} characters")
    return name


def start_session(user):
    session.clear()
    session["user_id"] = user.id
    session.permanent = True


@api.post("/register")
def register():
    user = User(id=User.new_id(), display_name=display_name_field())
    db.session.add(user)
    db.session.commit()
    start_session(user)
    return jsonify(user.to_dict()), 201


@api.post("/login")
def login():
    user = db.session.get(User, json_field("id").lower())
    if user is None:
        abort(401, "unknown login id")
    start_session(user)
    return jsonify(user.to_dict())


@api.post("/logout")
def logout():
    session.clear()
    return "", 204


@api.get("/me")
@login_required
def me(user):
    return jsonify(user.to_dict())


@api.get("/rooms")
@login_required
def list_rooms(user):
    rooms = db.session.scalars(db.select(Room).order_by(Room.display_name))
    return jsonify([room.to_dict(user) for room in rooms])


@api.post("/rooms")
@login_required
def create_room(user):
    name = display_name_field()
    if db.session.scalar(db.select(Room).filter_by(display_name=name)) is not None:
        abort(409, "a room with that name already exists")
    room = Room(display_name=name)
    user.rooms.append(room)
    db.session.commit()
    socket.emit("rooms_changed")
    return jsonify(room.to_dict(user)), 201


@api.post("/rooms/<int:room_id>/join")
@login_required
def join(user, room_id):
    room = db.get_or_404(Room, room_id, description="room not found")
    if room not in user.rooms:
        user.rooms.append(room)
        db.session.commit()
    return jsonify(room.to_dict(user))


@api.post("/rooms/<int:room_id>/leave")
@login_required
def leave(user, room_id):
    room = db.get_or_404(Room, room_id, description="room not found")
    if room in user.rooms:
        user.rooms.remove(room)
        db.session.commit()
    return jsonify(room.to_dict(user))


@api.get("/rooms/<int:room_id>/permission")
@login_required
def permission(user, room_id):
    room = db.get_or_404(Room, room_id, description="room not found")
    return jsonify(room_id=room.id, permission=user.permission(room))


@api.get("/rooms/<int:room_id>/messages")
@login_required
def messages(user, room_id):
    room = db.get_or_404(Room, room_id, description="room not found")
    if user.permission(room) != Permission.MEMBER:
        abort(403, "join the room to read its messages")
    latest = db.session.scalars(
        db.select(Message)
        .filter_by(room_id=room.id)
        .order_by(Message.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    return jsonify([message.to_dict() for message in reversed(latest)])
