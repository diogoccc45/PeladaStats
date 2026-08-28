"""
Restores match history from a workbook produced by xlsx_export.py's "Jogos"
sheet — the counterpart to a reset, for undoing one or bringing back an
older season.

This REPLACES all current match data (matches, match_stats, overall_history,
comments) with what's in the file — it's a restore, not a merge. Players are
matched by username, which must already exist in this database (accounts
aren't touched by a reset, so this is normally guaranteed).
"""

from openpyxl import load_workbook

from xlsx_export import JOGOS_HEADERS


class ImportError_(Exception):
    """Raised for any problem with the uploaded file — message is safe to show the admin."""


def _parse_bool(value):
    return str(value).strip().lower() in ("sim", "true", "1", "yes")


def import_matches_from_workbook(db, file_stream):
    try:
        wb = load_workbook(file_stream, data_only=True)
    except Exception:
        raise ImportError_("Não consegui abrir o ficheiro — confirma que é um .xlsx válido.")

    if "Jogos" not in wb.sheetnames:
        raise ImportError_('O ficheiro não tem uma folha "Jogos" — não parece ser uma exportação da PeladaStats.')
    ws = wb["Jogos"]

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ImportError_('A folha "Jogos" está vazia.')

    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    if header != JOGOS_HEADERS:
        raise ImportError_('O cabeçalho da folha "Jogos" não corresponde ao esperado — usa um ficheiro exportado por aqui, sem editar as colunas.')

    users_by_username = {r["username"]: r["id"] for r in db.execute("SELECT id, username FROM users")}

    matches_in_order = []
    match_rows = {}
    for raw in rows[1:]:
        if raw is None or raw[0] is None:
            continue
        (
            orig_match_id, match_date, location, score_a, score_b, status,
            _nickname, username, team, goals, assists,
            mvp_username, golo_username, submitted, created_by_username,
        ) = raw

        if username not in users_by_username:
            raise ImportError_(f'O username "{username}" da folha não existe nesta base de dados — importa depois de recriares essa conta, ou corrige a folha.')

        if orig_match_id not in match_rows:
            match_rows[orig_match_id] = {
                "match_date": str(match_date)[:10],
                "location": location or None,
                "team_a_score": int(score_a),
                "team_b_score": int(score_b),
                "status": status,
                "created_by": users_by_username.get(created_by_username) if created_by_username else None,
                "players": [],
            }
            matches_in_order.append(orig_match_id)

        match_rows[orig_match_id]["players"].append({
            "user_id": users_by_username[username],
            "team": team,
            "goals": int(goals or 0),
            "assists": int(assists or 0),
            "mvp_vote_for": users_by_username.get(mvp_username) if mvp_username else None,
            "goal_of_match_vote_for": users_by_username.get(golo_username) if golo_username else None,
            "submitted": 1 if _parse_bool(submitted) else 0,
        })

    db.execute("DELETE FROM comments")
    db.execute("DELETE FROM notifications")
    db.execute("DELETE FROM overall_history")
    db.execute("DELETE FROM match_stats")
    db.execute("DELETE FROM matches")
    db.commit()

    for orig_id in matches_in_order:
        m = match_rows[orig_id]
        cur = db.execute(
            """
            INSERT INTO matches (match_date, location, team_a_score, team_b_score, status, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (m["match_date"], m["location"], m["team_a_score"], m["team_b_score"], m["status"], m["created_by"]),
        )
        new_match_id = cur.lastrowid
        for p in m["players"]:
            db.execute(
                """
                INSERT INTO match_stats (match_id, user_id, team, goals, assists, mvp_vote_for, goal_of_match_vote_for, submitted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (new_match_id, p["user_id"], p["team"], p["goals"], p["assists"], p["mvp_vote_for"], p["goal_of_match_vote_for"], p["submitted"]),
            )
    db.commit()

    import stats as stats_mod
    stats_mod.recompute_all_overall(db)

    return {"matches": len(matches_in_order), "rows": len(rows) - 1}
