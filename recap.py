"""
Post-match recap ("fim de jogo"): the full-screen summary a player gets the
first time they open the app after a match they played in is confirmed —
result, how their Overall moved, their goals/assists/awards, how the
leaderboard shifted and whatever they unlocked.

Nothing extra is stored: the data is rebuilt on demand from the match,
overall_history (Overall + ranking) and the same unlock detection the
notifications use. "Not seen yet" is tracked on the existing
"Jogo confirmado" notification each participant already receives
(celebrated_at IS NULL), so there's no new table or migration.
"""
from overall_engine import OVERALL_START, compute_goal_of_match_winners, compute_match_mvps
import stats as stats_mod

# Older confirmations never pop up on their own (the match page still has a button).
RECAP_FRESH_DAYS = 7

# Label prefix of the "match confirmed" notification (see matches.notify_match_confirmed);
# it only matches the first row of the batch — the MVP/Golo lines have their own labels.
RECAP_LABEL_PREFIX = "Jogo confirmado:"

_RECAP_NOTIFICATION_WHERE = (
    "user_id = ? AND kind = 'reminder' AND label LIKE ? AND match_id IS NOT NULL AND celebrated_at IS NULL"
)
_FRESH_WHERE = f"created_at >= datetime('now', '-{RECAP_FRESH_DAYS} days')"


def pending_recap_match_id(db, user_id):
    """The match whose recap this player hasn't seen yet — the most recent
    one if several are waiting (we never stack popups). None if nothing is."""
    row = db.execute(
        f"SELECT match_id FROM notifications WHERE {_RECAP_NOTIFICATION_WHERE} AND {_FRESH_WHERE} ORDER BY id DESC LIMIT 1",
        (user_id, RECAP_LABEL_PREFIX + "%"),
    ).fetchone()
    return row["match_id"] if row else None


def mark_recaps_seen(db, user_id):
    """Marks every waiting recap as seen (called when the popup opens)."""
    db.execute(
        f"UPDATE notifications SET celebrated_at = CURRENT_TIMESTAMP WHERE {_RECAP_NOTIFICATION_WHERE}",
        (user_id, RECAP_LABEL_PREFIX + "%"),
    )
    db.commit()


def build_recap(db, match_id, user_id):
    """JSON-ready dict for the overlay, or None if the match isn't confirmed
    or this player didn't play in it."""
    match = db.execute("SELECT * FROM matches WHERE id = ? AND status = 'confirmado'", (match_id,)).fetchone()
    if match is None:
        return None
    rows = db.execute("SELECT * FROM match_stats WHERE match_id = ?", (match_id,)).fetchall()
    me = next((r for r in rows if r["user_id"] == user_id), None)
    if me is None:
        return None

    recap = {
        "match": {
            "id": match_id,
            "date": str(match["match_date"]),
            "location": match["location"],
            "score_a": match["team_a_score"],
            "score_b": match["team_b_score"],
        },
        "my_team": me["team"],
        "result": stats_mod._result_for(me, match),
        "goals": me["goals"],
        "assists": me["assists"],
        "was_mvp": user_id in compute_match_mvps(rows),
        "was_golo": user_id in compute_goal_of_match_winners(rows),
        "overall": None,
        "rank": None,
        "unlocks": [],
    }

    movement = stats_mod.get_rank_movement(db, match_id)
    if movement is not None:
        before = movement["overall_before"].get(user_id, OVERALL_START)
        after = movement["overall_after"].get(user_id, OVERALL_START)
        recap["overall"] = {"before": round(before, 2), "after": round(after, 2), "delta": round(after - before, 2)}
        recap["rank"] = {
            "before": movement["rank_before"][user_id],
            "after": movement["rank_after"][user_id],
            "change": movement["change"][user_id],
        }

    for u in stats_mod._detect_unlocks(db, match_id):
        if u["user_id"] == user_id:
            recap["unlocks"].append({"kind": u["kind"], "icon": u["icon"], "label": u["label"], "no_bonus": u["no_bonus"]})

    return recap
