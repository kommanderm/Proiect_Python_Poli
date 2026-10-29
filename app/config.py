from datetime import timedelta


SQLALCHEMY_DATABASE_URI="sqlite:///../db.sqlite"
SECRET_KEY="change_in_prod"
PERMANENT_SESSION_LIFETIME=timedelta(days=7)
