from flask import Blueprint
from flask_login import current_user, login_required

from database import get_db

bp = Blueprint("notifications", __name__, url_prefix="/notificacoes")


@bp.route("/marcar-vistas", methods=["POST"])
@login_required
def marcar_vistas():
    db = get_db()
    db.execute(
        "UPDATE notifications SET seen_at = CURRENT_TIMESTAMP WHERE user_id = ? AND seen_at IS NULL",
        (int(current_user.get_id()),),
    )
    db.commit()
    return ("", 204)
