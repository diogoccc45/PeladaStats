from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

import stats as stats_mod
from database import delete_user_cascade, get_db

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _require_admin():
    if not current_user.is_admin:
        abort(403)


@bp.route("/")
@login_required
def painel():
    _require_admin()
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY nickname").fetchall()
    summaries = stats_mod.get_all_summaries(db)

    players = [{"user": u, "games": summaries.get(u["id"], {}).get("games", 0)} for u in users]
    return render_template("admin/painel.html", players=players)


@bp.route("/remover/<int:user_id>", methods=["POST"])
@login_required
def remover(user_id):
    _require_admin()
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    if user_id == int(current_user.get_id()):
        flash("Não podes remover a tua própria conta por aqui.")
        return redirect(url_for("admin.painel"))

    delete_user_cascade(db, user_id)
    flash(f"{user['nickname']} foi removido.")
    return redirect(url_for("admin.painel"))
