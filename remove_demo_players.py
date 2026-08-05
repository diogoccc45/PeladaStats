"""
One-time cleanup: remove the demo/seed players (rafa, diogo, tomas) and
everything tied to them, now that real players have started registering.

Run from the project root (same folder as peladastats.db):
    python3 remove_demo_players.py
"""
import sqlite3

DEMO_USERNAMES = ("rafa", "diogo", "tomas")

con = sqlite3.connect("peladastats.db")
con.execute("PRAGMA foreign_keys = ON")

placeholders = ",".join("?" * len(DEMO_USERNAMES))
rows = con.execute(
    f"SELECT id, username FROM users WHERE username IN ({placeholders})",
    DEMO_USERNAMES,
).fetchall()

if not rows:
    print("No demo players found — nothing to do.")
else:
    demo_ids = [r[0] for r in rows]
    id_placeholders = ",".join("?" * len(demo_ids))

    # Clear any MVP vote pointing at a demo player, cast by anyone — avoids
    # a foreign-key error regardless of who cast the vote.
    con.execute(
        f"UPDATE match_stats SET mvp_vote_for = NULL WHERE mvp_vote_for IN ({id_placeholders})",
        demo_ids,
    )

    # match_stats/overall_history/comments would cascade from the schema's
    # ON DELETE CASCADE anyway, but being explicit keeps this script correct
    # even if that ever changes.
    con.execute(f"DELETE FROM match_stats WHERE user_id IN ({id_placeholders})", demo_ids)
    con.execute(f"DELETE FROM overall_history WHERE user_id IN ({id_placeholders})", demo_ids)
    con.execute(f"DELETE FROM comments WHERE user_id IN ({id_placeholders})", demo_ids)

    # Remove any match now left with zero players — i.e. it only ever
    # involved demo players.
    con.execute(
        "DELETE FROM matches WHERE id NOT IN (SELECT DISTINCT match_id FROM match_stats)"
    )

    con.execute(f"DELETE FROM users WHERE id IN ({id_placeholders})", demo_ids)
    con.commit()

    for _id, username in rows:
        print(f"Removed: {username}")
    print("Done.")

con.close()
