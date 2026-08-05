# PeladaStats

A mobile-first stats platform for weekly 5-a-side football with friends. Every player
gets a profile with an EA Sports FC-inspired rating card; every match feeds a live
leaderboard, an evolving Overall rating, records, and achievements.

Built with Flask + SQLite (no ORM, raw SQL) + Jinja2 + TailwindCSS + Chart.js.

## Quickstart

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

flask --app app init-db         # creates the tables (wipes existing data)
flask --app app seed-demo       # optional: 3 demo players + 1 confirmed match
flask --app app run --debug
```

Open http://127.0.0.1:5000. Register a new player, or if you ran `seed-demo`,
log in as `rafa` / `diogo` / `tomas` with password `pelada123`.

## Features

**Auth** — username + password (hashed with werkzeug), no email required.
Registration is a 3-step wizard with a live-building player card preview.

**Dashboard** — featured "Player of the moment" card, a full sortable stats
table, a banner when matches are waiting on your input, and an Overall trend
arrow (▲/▼) showing the change since each player's last match.

**Matches** (`/jogos`) — create a match (date, location, team rosters,
final score); each player fills in only their own goals/assists/MVP vote
(never for themselves). A match auto-confirms once everyone has submitted —
there's no goal-sum validation gate, since with a small group of friends
honest self-reporting is enough. Players can correct their own entry until
the match confirms, after which it locks. Confirmed matches show a
"Match Facts" panel (MVP + top scorer).

**Overall rating engine** (`overall_engine.py`) — every player starts at 65.
Per confirmed match: win +0.20, goal +0.15 each, assist +0.10 each, match
MVP +0.30 (ties in the vote count award nobody); loss -0.20, a goalless/
assistless game -0.15, zero MVP votes received -0.10. Positive deltas only
are scaled by a progressive-difficulty multiplier based on the player's
Overall going into the match (easier low, harder high), so climbing to 99
takes real, sustained form. Overall is clamped to 50-99 and never drops
below 50. Full math and rationale are documented in the module itself.

**Forma, Records, Achievements, Head-to-head** (`stats.py`) — form is based
on the last 5 confirmed matches; records track single-game bests (goals,
assists, goal involvements) and the longest win/loss/MVP streaks; 10 fixed
achievements unlock automatically; head-to-head compares two players'
career totals side by side.

**Profile** (`/perfil`) — full stat breakdown, general-ranking position,
progress bar toward the closest numeric achievement, 3 Chart.js evolution
graphs (Overall, cumulative goals, cumulative assists), and a full match
history.

**Settings** (`/definicoes`) — edit nickname, preferred foot, favourite
player/team (name + image URL, no upload/storage — just paste a link);
drag-to-reposition + zoom image cropper for both photos; light/dark theme
toggle (persisted in `localStorage`).

**Design** — dark mode by default with a light theme, FIFA-card-style
featured cards with an animated sheen, a holographic overlay that kicks in
once a player's Overall hits 85+, and an EA Sports-style diagonal accent
band in the header.

## Project structure

```
app.py              Flask app factory, blueprint registration
config.py            App config (secret key, DB path)
database.py           DB connection helpers + CLI commands (init-db, seed-demo)
schema.sql            Table definitions
models.py             Flask-Login User wrapper
overall_engine.py      Overall rating math
stats.py              Shared stats: summaries, form, achievements, records, evolution series
auth.py / matches.py / profile.py / dashboard.py / records.py / comparar.py / settings.py
                      Blueprints, one per feature area
templates/            Jinja2 templates (base.html + base_app.html shell, then one folder/file per feature)
static/css/theme.css   All styling — design tokens as CSS variables, one theme file for the whole app
```

## Notable design decisions

- **SQLite + raw SQL, no ORM** — deliberate, to stay in Python/SQL rather than
  add an ORM layer.
- **MVP ties award nobody** — if two or more players tie for most votes in a
  match, nobody gets the MVP bonus that game, rather than splitting it.
- **Progressive difficulty only dampens positive deltas** — penalties always
  apply at full strength, regardless of a player's current Overall.
- **No goal-sum validation** — removed on request; a small trusted group
  doesn't need it, and the score entered at match creation is informational
  only.
- **Overall stored as a float, always displayed rounded** — internal
  precision keeps the long-run progression accurate; every on-screen number
  rounds to the nearest whole unit (standard rounding, not floor). Sorting
  and ranking always use the true unrounded value so a display-rounding tie
  never picks the wrong "top player."
- **Image cropping uses literal `background-size` percentages**, not a true
  `cover`-equivalent baseline computed from each image's natural aspect
  ratio — simple and works well for the roughly-square photos/logos this
  app expects; a very non-square image may need a bit of extra zoom to
  fully fill the frame.

## Deployment

Planned target: PythonAnywhere's free tier (persistent disk, so SQLite
survives; the per-day CPU-second limit doesn't apply to web apps, only to
consoles/scheduled/always-on tasks). The free web app needs a quick
"extend" click roughly once a month or it goes offline (nothing is lost —
reactivating brings it straight back).

## Roadmap

- Show each player's Overall swing from `overall_history` directly on the
  confirmed match page (the data's already there).
- No way to edit or delete a mistakenly-created match yet.
- No pagination — irrelevant at this group's scale, but would matter if it
  ever grew a lot.
