"""
Builds the "export everything" workbook for the admin danger zone.

Two sheets:
  - "Estatísticas": one row per player, every aggregate stat, personal
    record, and achievement — a human-readable season summary.
  - "Jogos": one row per (match, player) — the raw data needed to fully
    reconstruct matches + match_stats later via xlsx_import.py. Players are
    referenced by username, not raw database id, so the file stays valid
    even if it's imported into a database where ids don't line up exactly
    the same way (as long as the usernames still exist).

Values are written as plain numbers/text, not formulas — this is a
point-in-time snapshot/backup, not a model meant to keep recalculating.
"""

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import stats as stats_mod

HEADER_FILL = PatternFill(start_color="1B2743", end_color="1B2743", fill_type="solid")
HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFF")
BODY_FONT = Font(name="Arial")

# Personal-best columns pulled straight from the leaderboards used by the
# Recordes popup — each player's own value for that category.
PERSONAL_RECORD_COLUMNS = [
    ("best_goals", "Recorde pessoal — golos num jogo"),
    ("best_assists", "Recorde pessoal — assistências num jogo"),
    ("best_involvement", "Recorde pessoal — participações num jogo"),
    ("win_streak", "Maior sequência de vitórias"),
    ("loss_streak", "Maior sequência de derrotas"),
    ("mvp_streak", "Maior sequência de MVP"),
]

# Categories eligible to appear in the "Recordes que detém" summary column —
# whoever is #1 in the leaderboard for a category gets it listed here.
GLOBAL_RECORD_LABELS = {
    "best_goals": "Mais golos num jogo",
    "best_assists": "Mais assistências num jogo",
    "best_involvement": "Mais participações num jogo",
    "win_streak": "Maior sequência de vitórias",
    "loss_streak": "Maior sequência de derrotas",
    "mvp_streak": "Mais MVP consecutivos",
    "most_games": "Mais jogos disputados",
    "top_goals_season": "Mais golos na época",
    "top_assists_season": "Mais assistências na época",
    "top_involvement_season": "Mais participações na época",
    "top_mvp_season": "Mais MVPs na época",
}

# Column headers for the "Jogos" sheet — xlsx_import.py depends on this
# exact order (it reads by position for speed, and checks these names on
# the header row to confirm the file is really a PeladaStats export).
JOGOS_HEADERS = [
    "Match ID (original)", "Data", "Local", "Golos Equipa A", "Golos Equipa B", "Estado",
    "Alcunha", "Username", "Equipa", "Golos", "Assistências",
    "Votou MVP em (username)", "Votou Golo da Jornada em (username)", "Submetido",
    "Criado por (username)",
]


def _style_header_row(ws, row, n_cols):
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _autosize(ws, headers):
    for i, header in enumerate(headers, start=1):
        col_letter = get_column_letter(i)
        ws.column_dimensions[col_letter].width = min(max(len(str(header)), 10) + 4, 34)


def _build_estatisticas_sheet(wb, db, users, summaries, records):
    ws = wb.active
    ws.title = "Estatísticas"

    holders = {}
    for key, label in GLOBAL_RECORD_LABELS.items():
        rec = records[key]
        if rec["user_id"] is not None and rec["value"] > 0:
            holders.setdefault(rec["user_id"], []).append(label)

    ranked = sorted(users, key=lambda u: u["overall"], reverse=True)
    rank_by_id = {u["id"]: i + 1 for i, u in enumerate(ranked)}

    headers = [
        "Posição", "Alcunha", "Username", "Overall", "Forma atual",
        "Jogos", "Vitórias", "Empates", "Derrotas",
        "Golos", "Assistências", "Participações em golo",
        "Média golos/jogo", "Média assist./jogo",
        "MVP (vezes)", "Golo da Jornada (vezes)",
    ]
    headers += [label for _, label in PERSONAL_RECORD_COLUMNS]
    headers += [a["label"] for a in stats_mod.ACHIEVEMENTS]
    headers.append("Recordes do grupo que detém")

    ws.append(headers)
    _style_header_row(ws, 1, len(headers))
    ws.freeze_panes = "A2"

    for u in users:
        uid = u["id"]
        s = summaries[uid]
        achievements = stats_mod.get_achievements(s)
        unlocked_ids = {a["id"] for a in achievements if a["unlocked"]}

        row = [
            rank_by_id[uid], u["nickname"], u["username"], round(u["overall"], 2), s["form"]["label"],
            s["games"], s["wins"], s["draws"], s["losses"],
            s["goals"], s["assists"], s["goal_involvements"],
            round(s["avg_goals"], 2), round(s["avg_assists"], 2),
            s["mvp"], s["golo_da_jornada"],
        ]
        for key, _ in PERSONAL_RECORD_COLUMNS:
            entry = next((r for r in records["leaderboards"][key] if r["user_id"] == uid), None)
            row.append(entry["value"] if entry else 0)
        for a in stats_mod.ACHIEVEMENTS:
            row.append("Sim" if a["id"] in unlocked_ids else "Não")
        row.append(", ".join(holders.get(uid, [])) or "—")

        ws.append(row)

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = BODY_FONT
    _autosize(ws, headers)


def _build_jogos_sheet(wb, db, users_by_id):
    ws = wb.create_sheet("Jogos")
    ws.append(JOGOS_HEADERS)
    _style_header_row(ws, 1, len(JOGOS_HEADERS))
    ws.freeze_panes = "A2"

    matches = db.execute("SELECT * FROM matches ORDER BY match_date ASC, id ASC").fetchall()
    for m in matches:
        rows = db.execute(
            "SELECT * FROM match_stats WHERE match_id = ? ORDER BY id ASC", (m["id"],)
        ).fetchall()
        created_by_username = None
        if m["created_by"] is not None and m["created_by"] in users_by_id:
            created_by_username = users_by_id[m["created_by"]]["username"]

        for r in rows:
            player = users_by_id.get(r["user_id"])
            if player is None:
                continue  # jogador entretanto removido — não há username para gravar
            mvp_username = users_by_id[r["mvp_vote_for"]]["username"] if r["mvp_vote_for"] in users_by_id else ""
            golo_username = (
                users_by_id[r["goal_of_match_vote_for"]]["username"]
                if r["goal_of_match_vote_for"] in users_by_id else ""
            )
            ws.append([
                m["id"], str(m["match_date"]), m["location"] or "",
                m["team_a_score"], m["team_b_score"], m["status"],
                player["nickname"], player["username"], r["team"],
                r["goals"], r["assists"], mvp_username, golo_username,
                "Sim" if r["submitted"] else "Não", created_by_username or "",
            ])

    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.font = BODY_FONT
    _autosize(ws, JOGOS_HEADERS)


def build_stats_workbook(db):
    users = db.execute("SELECT * FROM users ORDER BY nickname").fetchall()
    users_by_id = {u["id"]: u for u in users}
    summaries = stats_mod.get_all_summaries(db)
    records = stats_mod.get_records(db)

    wb = Workbook()
    _build_estatisticas_sheet(wb, db, users, summaries, records)
    _build_jogos_sheet(wb, db, users_by_id)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
