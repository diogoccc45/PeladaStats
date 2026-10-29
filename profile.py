import json

from flask import Blueprint, Response, abort, render_template
from flask_login import current_user, login_required

import stats as stats_mod
from card_generator import build_player_card
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
    movement = stats_mod.get_rank_movement(db)
    rank_change = movement["change"].get(user_id, 0) if movement else 0
    next_achievement = stats_mod.get_next_achievement(summary)

    return render_template(
        "profile.html",
        profile_user=user,
        summary=summary,
        achievements=achievements,
        evolution_json=json.dumps(evolution),
        avg_window=stats_mod.PER_GAME_AVG_WINDOW,
        is_me=(user_id == int(current_user.get_id())),
        rank=rank,
        rank_change=rank_change,
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


@bp.route("/<int:user_id>/cartao.png")
@login_required
def cartao(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    summary = stats_mod.get_player_summary(db, user_id)
    png_bytes = build_player_card(user, summary)
    return Response(
        png_bytes,
        mimetype="image/png",
        headers={"Content-Disposition": f'inline; filename="{user["nickname"]}-peladastats.png"'},
    )
