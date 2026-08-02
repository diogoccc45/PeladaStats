import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-muda-isto-em-producao")
    DATABASE = os.path.join(BASE_DIR, "peladastats.db")
