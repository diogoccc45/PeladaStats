from flask import Blueprint, current_app, request
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


@bp.route("/lembrete-semanal")
def lembrete_semanal():
    """Pinged by an external scheduler (e.g. cron-job.org), not by a logged-in
    user — that's why there's no @login_required here, just the secret token.
    Creates a "há jogo hoje" reminder for every registered player."""
    if request.args.get("token") != current_app.config["CRON_SECRET"]:
        return ("forbidden", 403)

    db = get_db()
    user_ids = [r["id"] for r in db.execute("SELECT id FROM users")]
    if user_ids:
        db.executemany(
            "INSERT INTO notifications (user_id, kind, label) VALUES (?, 'reminder', ?)",
            [(uid, "Hoje há jogo! Estás preparado?") for uid in user_ids],
        )
        db.commit()
    return ("ok", 200)
