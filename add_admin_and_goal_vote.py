"""
One-time migration: adds the columns needed for the admin feature and the
Golo da Jornada vote, then makes diogocc45 an admin.

Run from the project root (same folder as peladastats.db):
    python3 add_admin_and_goal_vote.py
"""
import sqlite3

ADMIN_USERNAME = "diogocc45"

con = sqlite3.connect("peladastats.db")

columns = [row[1] for row in con.execute("PRAGMA table_info(users)")]
if "is_admin" not in columns:
    con.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    print("Added is_admin column to users.")
else:
    print("is_admin already exists — skipped.")

columns = [row[1] for row in con.execute("PRAGMA table_info(match_stats)")]
if "goal_of_match_vote_for" not in columns:
    con.execute("ALTER TABLE match_stats ADD COLUMN goal_of_match_vote_for INTEGER REFERENCES users(id)")
    print("Added goal_of_match_vote_for column to match_stats.")
else:
    print("goal_of_match_vote_for already exists — skipped.")

con.commit()

row = con.execute("SELECT id FROM users WHERE username = ?", (ADMIN_USERNAME,)).fetchone()
if row is None:
    print(f"No user with username '{ADMIN_USERNAME}' found — nobody was made admin. "
          f"Run this again after registering that account.")
else:
    con.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (row[0],))
    con.commit()
    print(f"Made '{ADMIN_USERNAME}' an admin.")

con.close()
