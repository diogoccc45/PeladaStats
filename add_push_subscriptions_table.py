"""
One-time migration: adds the push_subscriptions table (one row per device
that's opted in to real OS-level Web Push notifications).

Run from the project root (same folder as peladastats.db):
    python3 add_push_subscriptions_table.py
"""
import sqlite3

con = sqlite3.connect("peladastats.db")

tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
if "push_subscriptions" in tables:
    print("push_subscriptions table already exists — nothing to do.")
else:
    con.execute("""
        CREATE TABLE push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()
    print("Created push_subscriptions table.")

con.close()
