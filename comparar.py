from flask import Blueprint, render_template, request
from flask_login import login_required

import stats as stats_mod
from database import get_db

bp = Blueprint("comparar", __name__, url_prefix="/comparar")


@bp.route("/")
@login_required
def head_to_head():
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY nickname").fetchall()

    a_id = request.args.get("a", type=int)
    b_id = request.args.get("b", type=int)

    summaries = stats_mod.get_all_summaries(db)

    player_a = next((u for u in users if u["id"] == a_id), None) if a_id else None
    player_b = next((u for u in users if u["id"] == b_id), None) if b_id else None

    summary_a = summaries.get(a_id) if player_a else None
    summary_b = summaries.get(b_id) if player_b else None

    return render_template(
        "comparar.html",
        users=users,
        player_a=player_a,
        player_b=player_b,
        summary_a=summary_a,
        summary_b=summary_b,
    )
