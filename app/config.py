from datetime import timedelta


SQLALCHEMY_DATABASE_URI="sqlite:///../db.sqlite"
SECRET_KEY="change_in_prod"
PERMANENT_SESSION_LIFETIME=timedelta(days=7)
# request bodies are small JSON objects; anything bigger gets a 413
MAX_CONTENT_LENGTH=16*1024
