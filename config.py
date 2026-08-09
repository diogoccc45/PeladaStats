import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-muda-isto-em-producao")
    DATABASE = os.path.join(BASE_DIR, "peladastats.db")
    # Shared code friends need to know to register — set a real one via the
    # WSGI file on PythonAnywhere, same way as SECRET_KEY.
    INVITE_CODE = os.environ.get("INVITE_CODE", "muda-este-codigo")
