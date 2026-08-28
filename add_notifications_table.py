"""
One-time migration: adds the notifications table — achievement/record
unlocks (kind='unlock', drive the confetti + toast) and match-created
reminders (kind='reminder', "fill in your stats"), both surfaced in the
notifications bell in the top bar.

Run from the project root (same folder as peladastats.db):
    python3 add_notifications_table.py
"""
import sqlite3

con = sqlite3.connect("peladastats.db")

tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
if "notifications" in tables:
    print("notifications table already exists — nothing to do.")
else:
    con.execute("""
        CREATE TABLE notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'unlock' CHECK(kind IN ('unlock', 'reminder')),
            label TEXT NOT NULL,
            match_id INTEGER REFERENCES matches(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            celebrated_at TIMESTAMP,
            seen_at TIMESTAMP
        )
    """)
    con.commit()
    print("Created notifications table.")

con.close()
