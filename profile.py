import json

from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

import stats as stats_mod
from database import get_db

bp = Blueprint("profile", __name__, url_prefix="/perfil")


def _render_profile(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)

    summary = stats_mod.get_player_summary(db, user_id)
    achievements = stats_mod.get_achievements(summary)
    evolution = stats_mod.get_evolution_series(db, user_id, summary)
    rank = stats_mod.get_rank(db, user_id)
    next_achievement = stats_mod.get_next_achievement(summary)

    return render_template(
        "profile.html",
        profile_user=user,
        summary=summary,
        achievements=achievements,
        evolution_json=json.dumps(evolution),
        is_me=(user_id == int(current_user.get_id())),
        rank=rank,
        next_achievement=next_achievement,
    )


@bp.route("/")
@login_required
def me():
    return _render_profile(int(current_user.get_id()))


@bp.route("/<int:user_id>")
@login_required
def other(user_id):
    return _render_profile(user_id)
