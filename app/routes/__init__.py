from flask import Blueprint, render_template

from app.db import User
from app.routes.api import api

pages = Blueprint("pages", __name__)


@pages.get("/")
def index():
    user = User.from_session()
    if user is None:
        return render_template("login.html")
    return render_template("chat.html", user=user)
