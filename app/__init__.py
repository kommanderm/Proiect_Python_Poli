from flask import Flask
app=Flask(__name__)


app.config.from_pyfile("config.py")
# FLASK_* env vars override config.py, e.g. FLASK_SQLALCHEMY_DATABASE_URI (the tests use this)
app.config.from_prefixed_env()
from app.db import db



from app.socket import socket
from app.routes import api, pages

app.register_blueprint(pages)
app.register_blueprint(api)

with app.app_context():
    db.create_all()
