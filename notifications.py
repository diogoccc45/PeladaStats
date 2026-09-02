from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from database import get_db
from push import send_push_to_user

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


@bp.route("/push/subscrever", methods=["POST"])
@login_required
def push_subscrever():
    data = request.get_json(force=True, silent=True) or {}
    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")
    if not endpoint or not p256dh or not auth:
        return jsonify({"error": "dados de subscrição incompletos"}), 400

    db = get_db()
    db.execute(
        """
        INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (?, ?, ?, ?)
        ON CONFLICT(endpoint) DO UPDATE SET user_id = excluded.user_id, p256dh = excluded.p256dh, auth = excluded.auth
        """,
        (int(current_user.get_id()), endpoint, p256dh, auth),
    )
    db.commit()
    return ("", 204)


@bp.route("/push/cancelar", methods=["POST"])
@login_required
def push_cancelar():
    data = request.get_json(force=True, silent=True) or {}
    endpoint = data.get("endpoint")
    db = get_db()
    if endpoint:
        db.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = ? AND user_id = ?",
            (endpoint, int(current_user.get_id())),
        )
    else:
        db.execute("DELETE FROM push_subscriptions WHERE user_id = ?", (int(current_user.get_id()),))
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
    label = "Hoje é dia de pelada! Já votaste?"
    if user_ids:
        db.executemany(
            "INSERT INTO notifications (user_id, kind, label) VALUES (?, 'reminder', ?)",
            [(uid, label) for uid in user_ids],
        )
        db.commit()
        for uid in user_ids:
            send_push_to_user(uid, "⚽ PeladaStats", label)
    return ("ok", 200)
