import json

from flask import Blueprint, render_template
from flask_login import current_user, login_required

import stats as stats_mod
from database import get_db

bp = Blueprint("dashboard", __name__)


def initials(name):
    parts = (name or "?").strip().split()
    return "".join(p[0].upper() for p in parts[:2]) or "?"


@bp.route("/")
@login_required
def home():
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY nickname").fetchall()
    summaries = stats_mod.get_all_summaries(db)

    my_id = int(current_user.get_id())
    pending_matches = db.execute("SELECT id FROM matches WHERE status = 'pendente'").fetchall()
    pending_total = len(pending_matches)
    pending_mine = 0
    for m in pending_matches:
        row = db.execute(
            "SELECT submitted FROM match_stats WHERE match_id = ? AND user_id = ?",
            (m["id"], my_id),
        ).fetchone()
        if row is not None and not row["submitted"]:
            pending_mine += 1

    players = []
    for u in users:
        s = summaries.get(u["id"], {})
        form = s.get("form", {"label": "Sem jogos", "emoji": "⚪"})

        trend = stats_mod.get_last_delta(db, u["id"])
        if trend is None:
            trend_class, trend_display = "trend-flat", None
        elif trend > 0:
            trend_class, trend_display = "trend-up", f"▲{trend:.2f}"
        elif trend < 0:
            trend_class, trend_display = "trend-down", f"▼{abs(trend):.2f}"
        else:
            trend_class, trend_display = "trend-flat", "▬0.00"

        players.append(
            {
                "id": u["id"],
                "name": u["nickname"],
                "initials": initials(u["nickname"]),
                "photo": u["favorite_player_image_url"],
                "photo_zoom": round(u["favorite_player_image_zoom"] * 100),
                "photo_x": u["favorite_player_image_pos_x"],
                "photo_y": u["favorite_player_image_pos_y"],
                "overall": round(u["overall"]),
                "overall_raw": u["overall"],
                "trend_class": trend_class,
                "trend_display": trend_display,
                "goals": s.get("goals", 0),
                "assists": s.get("assists", 0),
                "involvements": s.get("goal_involvements", 0),
                "mvp": s.get("mvp", 0),
                "wins": s.get("wins", 0),
                "draws": s.get("draws", 0),
                "losses": s.get("losses", 0),
                "games": s.get("games", 0),
                "avg_goals": round(s.get("avg_goals", 0), 2),
                "avg_assists": round(s.get("avg_assists", 0), 2),
                "form_emoji": form["emoji"],
                "form_label": form["label"],
            }
        )

    players_sorted = sorted(players, key=lambda p: p["overall_raw"], reverse=True)
    top = players_sorted[0] if players_sorted else None

    return render_template(
        "dashboard.html",
        players_json=json.dumps(players),
        top=top,
        pending_total=pending_total,
        pending_mine=pending_mine,
    )
