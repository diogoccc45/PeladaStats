from flask import Blueprint, render_template
from flask_login import login_required

import json

import stats as stats_mod
from database import get_db

bp = Blueprint("records", __name__, url_prefix="/recordes")

# Categories that count towards "who holds the most records" — loss_streak
# is deliberately left out, nobody wants to be crowned for that.
POSITIVE_RECORD_KEYS = (
    "best_goals", "best_assists", "best_involvement", "win_streak", "mvp_streak", "most_games",
    "top_goals_season", "top_assists_season", "top_involvement_season", "top_mvp_season",
    "top_golo_da_jornada_season",
)


@bp.route("/")
@login_required
def lista():
    db = get_db()
    records = stats_mod.get_records(db)

    holder_counts = {}
    for key in POSITIVE_RECORD_KEYS:
        rec = records[key]
        if rec["user_id"] is not None and rec["value"] > 0:
            holder_counts[rec["user_id"]] = holder_counts.get(rec["user_id"], 0) + 1

    recordman = None
    if holder_counts:
        top_user_id = max(holder_counts, key=holder_counts.get)
        recordman = {"user": records["users"][top_user_id], "count": holder_counts[top_user_id]}

    return render_template(
        "records.html", records=records, recordman=recordman,
        leaderboards_json=json.dumps(records["leaderboards"]),
    )
