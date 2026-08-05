"""
One-time migration: add the created_by column to an existing matches table
(needed for the "only the creator can delete a match" feature).

Run from the project root (same folder as peladastats.db):
    python3 add_match_creator_column.py

Existing matches will have created_by = NULL, so the delete button simply
won't show for them — nobody accidentally deletes older history.
"""
import sqlite3

con = sqlite3.connect("peladastats.db")

columns = [row[1] for row in con.execute("PRAGMA table_info(matches)")]
if "created_by" in columns:
    print("created_by already exists — nothing to do.")
else:
    con.execute("ALTER TABLE matches ADD COLUMN created_by INTEGER REFERENCES users(id)")
    con.commit()
    print("Added created_by column to matches.")

con.close()
