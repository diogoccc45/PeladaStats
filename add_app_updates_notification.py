"""
One-time migration:
  - adds the app_meta table (tracks the last git commit we notified
    everyone about, for the automatic "Nova Atualização" notification)
  - widens the notifications.kind CHECK constraint to also allow 'update'
    (SQLite can't ALTER a CHECK constraint directly, so this recreates the
    table and copies every existing row across — nothing is lost)

Run from the project root (same folder as peladastats.db):
    python3 add_app_updates_notification.py
"""
import sqlite3

con = sqlite3.connect("peladastats.db")

tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]

if "app_meta" not in tables:
    con.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
    con.commit()
    print("Created app_meta table.")
else:
    print("app_meta table already exists — skipped.")

row = con.execute(
    "SELECT sql FROM sqlite_master WHERE type='table' AND name='notifications'"
).fetchone()
if row and "'update'" in row[0]:
    print("notifications.kind already allows 'update' — skipped.")
else:
    print("Recreating notifications table to allow the new 'update' kind...")
    con.execute("ALTER TABLE notifications RENAME TO notifications_old")
    con.execute("""
        CREATE TABLE notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'unlock' CHECK(kind IN ('unlock', 'reminder', 'update')),
            label TEXT NOT NULL,
            match_id INTEGER REFERENCES matches(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            celebrated_at TIMESTAMP,
            seen_at TIMESTAMP
        )
    """)
    con.execute("INSERT INTO notifications SELECT * FROM notifications_old")
    con.execute("DROP TABLE notifications_old")
    con.commit()
    print("Done — notifications table recreated, all existing rows preserved.")

con.close()
