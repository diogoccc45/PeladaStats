from flask_login import UserMixin

from database import get_db


class User(UserMixin):
    """Wrapper fino à volta de uma linha da tabela users, para o Flask-Login."""

    def __init__(self, row):
        self.row = row

    # Flask-Login usa isto como identificador de sessão
    def get_id(self):
        return str(self.row["id"])

    def __getattr__(self, item):
        # Permite fazer current_user.nickname, current_user.overall, etc.
        try:
            return self.row[item]
        except (IndexError, KeyError):
            raise AttributeError(item)

    @staticmethod
    def get(user_id):
        db = get_db()
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return User(row) if row else None

    @staticmethod
    def get_by_username(username):
        db = get_db()
        row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return User(row) if row else None
