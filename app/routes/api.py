from functools import wraps

from flask import Blueprint, abort, jsonify, request, session
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException

from app import validation
from app.db import Message, Permission, Room, User, db
from app.socket import socket

api = Blueprint("api", __name__, url_prefix="/api")

HISTORY_LIMIT = 100
# out-of-range ids get a 404 from the router instead of overflowing SQLite's INTEGER
ROOM = f"<int(min=1, max={validation.SQLITE_INTEGER_MAX}):room_id>"


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


def valid(check):
    """Run a validator from app.validation on the JSON body; invalid input becomes a 400."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "the request body must be a JSON object")
    try:
        return check(data)
    except validation.ValidationError as error:
        abort(400, str(error))


def start_session(user):
    session.clear()
    session["user_id"] = user.id
    session.permanent = True


@api.post("/register")
def register():
    user = User(id=User.new_id(), display_name=valid(validation.display_name))
    db.session.add(user)
    db.session.commit()
    start_session(user)
    return jsonify(user.to_dict()), 201


@api.post("/login")
def login():
    user = db.session.get(User, valid(validation.login_id))
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
    name = valid(validation.display_name)
    # "General" and "general" would be two rooms nobody can tell apart
    taken = {existing.casefold() for existing in db.session.scalars(db.select(Room.display_name))}
    if name.casefold() in taken:
        abort(409, "a room with that name already exists")
    room = Room(display_name=name)
    user.rooms.append(room)
    try:
        db.session.commit()
    except IntegrityError:  # created by someone else in the meantime
        db.session.rollback()
        abort(409, "a room with that name already exists")
    socket.emit("rooms_changed")
    return jsonify(room.to_dict(user)), 201


@api.post(f"/rooms/{ROOM}/join")
@login_required
def join(user, room_id):
    room = db.get_or_404(Room, room_id, description="room not found")
    if room not in user.rooms:
        user.rooms.append(room)
        db.session.commit()
    return jsonify(room.to_dict(user))


@api.post(f"/rooms/{ROOM}/leave")
@login_required
def leave(user, room_id):
    room = db.get_or_404(Room, room_id, description="room not found")
    if room in user.rooms:
        user.rooms.remove(room)
        db.session.commit()
    return jsonify(room.to_dict(user))


@api.get(f"/rooms/{ROOM}/permission")
@login_required
def permission(user, room_id):
    room = db.get_or_404(Room, room_id, description="room not found")
    return jsonify(room_id=room.id, permission=user.permission(room))


@api.get(f"/rooms/{ROOM}/messages")
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
