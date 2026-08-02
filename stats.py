"""
Cálculos partilhados entre o dashboard, o perfil, os recordes e a comparação.

Tudo parte de get_confirmed_matches_with_stats(): a lista de jogos confirmados,
cada um com as respetivas linhas de match_stats. A partir daí construímos, por
jogador, uma "timeline" cronológica (resultado, golos, assistências, se foi MVP
nesse jogo) que serve de base a tudo o resto — forma, streaks para recordes, e
as séries dos gráficos de evolução.
"""

from overall_engine import OVERALL_START, compute_match_mvps

FORM_LEVELS = [
    (0.8, "Excelente", "🔥"),
    (0.6, "Boa", "🟢"),
    (0.4, "Normal", "🟡"),
    (0.2, "Fraca", "🟠"),
    (0.0, "Péssima", "🔴"),
]

ACHIEVEMENTS = [
    {"id": "primeiro_golo", "label": "Primeiro golo", "icon": "⚽", "check": lambda s: s["goals"] >= 1},
    {"id": "primeira_assistencia", "label": "Primeira assistência", "icon": "🎯", "check": lambda s: s["assists"] >= 1},
    {"id": "primeiro_mvp", "label": "Primeiro MVP", "icon": "⭐", "check": lambda s: s["mvp"] >= 1},
    {"id": "10_golos", "label": "10 golos", "icon": "⚽", "check": lambda s: s["goals"] >= 10, "metric": "goals", "threshold": 10},
    {"id": "25_golos", "label": "25 golos", "icon": "⚽", "check": lambda s: s["goals"] >= 25, "metric": "goals", "threshold": 25},
    {"id": "50_golos", "label": "50 golos", "icon": "⚽", "check": lambda s: s["goals"] >= 50, "metric": "goals", "threshold": 50},
    {"id": "25_assistencias", "label": "25 assistências", "icon": "🎯", "check": lambda s: s["assists"] >= 25, "metric": "assists", "threshold": 25},
    {"id": "10_vitorias", "label": "10 vitórias", "icon": "🏆", "check": lambda s: s["wins"] >= 10, "metric": "wins", "threshold": 10},
    {"id": "hat_trick", "label": "Hat-trick", "icon": "🎩", "check": lambda s: s["hat_trick"]},
    {"id": "100_participacoes", "label": "100 participações em golo", "icon": "🔥", "check": lambda s: s["goal_involvements"] >= 100, "metric": "goal_involvements", "threshold": 100},
]


def _result_for(row, match):
    if match["team_a_score"] == match["team_b_score"]:
        return "draw"
    if (row["team"] == "A" and match["team_a_score"] > match["team_b_score"]) or (
        row["team"] == "B" and match["team_b_score"] > match["team_a_score"]
    ):
        return "win"
    return "loss"


def get_confirmed_matches_with_stats(db):
    """[(match_row, [match_stats_rows]), ...] ordenado do jogo mais antigo para o mais recente."""
    matches = db.execute(
        "SELECT * FROM matches WHERE status = 'confirmado' ORDER BY match_date ASC, id ASC"
    ).fetchall()
    out = []
    for m in matches:
        rows = db.execute("SELECT * FROM match_stats WHERE match_id = ?", (m["id"],)).fetchall()
        out.append((m, rows))
    return out


def compute_match_mvp_map(matches_with_stats):
    """{match_id: {user_id que foi MVP nesse jogo}}"""
    return {m["id"]: compute_match_mvps(rows) for m, rows in matches_with_stats}


def longest_streak(items, predicate):
    best = cur = 0
    for it in items:
        if predicate(it):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def compute_form(timeline):
    recent = timeline[-5:]
    if not recent:
        return {"label": "Sem jogos", "emoji": "⚪", "ratio": None}
    points = sum(2 if g["result"] == "win" else (1 if g["result"] == "draw" else 0) for g in recent)
    ratio = points / (2 * len(recent))
    for threshold, label, emoji in FORM_LEVELS:
        if ratio >= threshold:
            return {"label": label, "emoji": emoji, "ratio": ratio}
    return {"label": "Péssima", "emoji": "🔴", "ratio": ratio}


def summarize_user(user_id, matches_with_stats, mvp_map):
    games = wins = losses = draws = goals = assists = mvp_count = 0
    timeline = []

    for m, rows in matches_with_stats:
        row = next((r for r in rows if r["user_id"] == user_id), None)
        if row is None or not row["submitted"]:
            continue
        result = _result_for(row, m)
        was_mvp = user_id in mvp_map.get(m["id"], set())

        games += 1
        goals += row["goals"]
        assists += row["assists"]
        if result == "win":
            wins += 1
        elif result == "loss":
            losses += 1
        else:
            draws += 1
        if was_mvp:
            mvp_count += 1

        timeline.append(
            {
                "match_id": m["id"],
                "date": str(m["match_date"]),
                "location": m["location"],
                "result": result,
                "goals": row["goals"],
                "assists": row["assists"],
                "was_mvp": was_mvp,
            }
        )

    goal_involvements = goals + assists
    summary = {
        "games": games,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "goals": goals,
        "assists": assists,
        "mvp": mvp_count,
        "goal_involvements": goal_involvements,
        "avg_goals": (goals / games) if games else 0,
        "avg_assists": (assists / games) if games else 0,
        "hat_trick": any(t["goals"] >= 3 for t in timeline),
        "timeline": timeline,
    }
    summary["form"] = compute_form(timeline)
    return summary


def get_all_summaries(db):
    """{user_id: summary} para todos os jogadores, calculado a partir de um único varrimento dos jogos confirmados."""
    matches_with_stats = get_confirmed_matches_with_stats(db)
    mvp_map = compute_match_mvp_map(matches_with_stats)
    user_ids = [r["id"] for r in db.execute("SELECT id FROM users").fetchall()]
    return {uid: summarize_user(uid, matches_with_stats, mvp_map) for uid in user_ids}


def get_player_summary(db, user_id):
    matches_with_stats = get_confirmed_matches_with_stats(db)
    mvp_map = compute_match_mvp_map(matches_with_stats)
    return summarize_user(user_id, matches_with_stats, mvp_map)


def get_achievements(summary):
    return [
        {"id": a["id"], "label": a["label"], "icon": a["icon"], "unlocked": bool(a["check"](summary))}
        for a in ACHIEVEMENTS
    ]


def get_next_achievement(summary):
    """Achievement numérica ainda por desbloquear mais próxima de o ser (para a barra de progresso).
    Ignora as achievements binárias (primeiro golo/assistência/MVP, hat-trick) — não têm progresso, só sim/não.
    Devolve None se não houver nenhuma numérica por desbloquear."""
    candidates = []
    for a in ACHIEVEMENTS:
        if "metric" not in a:
            continue
        current = summary[a["metric"]]
        if current >= a["threshold"]:
            continue
        candidates.append(
            {
                "id": a["id"],
                "label": a["label"],
                "icon": a["icon"],
                "current": current,
                "threshold": a["threshold"],
                "ratio": current / a["threshold"],
            }
        )
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["ratio"])


def get_rank(db, user_id):
    """Posição (1 = primeiro) deste jogador no ranking geral por Overall."""
    rows = db.execute("SELECT id FROM users ORDER BY overall DESC, id ASC").fetchall()
    for i, r in enumerate(rows):
        if r["id"] == user_id:
            return i + 1
    return None


def get_records(db):
    matches_with_stats = get_confirmed_matches_with_stats(db)
    mvp_map = compute_match_mvp_map(matches_with_stats)
    users = {r["id"]: r for r in db.execute("SELECT * FROM users").fetchall()}
    summaries = {uid: summarize_user(uid, matches_with_stats, mvp_map) for uid in users}

    best_goals = best_assists = best_involvement = None
    for m, rows in matches_with_stats:
        for r in rows:
            if not r["submitted"]:
                continue
            entry_goals = {"value": r["goals"], "user_id": r["user_id"], "date": str(m["match_date"])}
            entry_assists = {"value": r["assists"], "user_id": r["user_id"], "date": str(m["match_date"])}
            entry_inv = {"value": r["goals"] + r["assists"], "user_id": r["user_id"], "date": str(m["match_date"])}
            if best_goals is None or entry_goals["value"] > best_goals["value"]:
                best_goals = entry_goals
            if best_assists is None or entry_assists["value"] > best_assists["value"]:
                best_assists = entry_assists
            if best_involvement is None or entry_inv["value"] > best_involvement["value"]:
                best_involvement = entry_inv

    win_streak = {"value": 0, "user_id": None}
    loss_streak = {"value": 0, "user_id": None}
    mvp_streak = {"value": 0, "user_id": None}
    for uid, s in summaries.items():
        w = longest_streak(s["timeline"], lambda t: t["result"] == "win")
        l = longest_streak(s["timeline"], lambda t: t["result"] == "loss")
        mv = longest_streak(s["timeline"], lambda t: t["was_mvp"])
        if w > win_streak["value"]:
            win_streak = {"value": w, "user_id": uid}
        if l > loss_streak["value"]:
            loss_streak = {"value": l, "user_id": uid}
        if mv > mvp_streak["value"]:
            mvp_streak = {"value": mv, "user_id": uid}

    return {
        "best_goals": best_goals,
        "best_assists": best_assists,
        "best_involvement": best_involvement,
        "win_streak": win_streak,
        "loss_streak": loss_streak,
        "mvp_streak": mvp_streak,
        "users": users,
    }


def get_evolution_series(db, user_id, summary):
    overall_rows = db.execute(
        """
        SELECT oh.overall_after, m.match_date
        FROM overall_history oh
        JOIN matches m ON m.id = oh.match_id
        WHERE oh.user_id = ?
        ORDER BY m.match_date ASC, oh.id ASC
        """,
        (user_id,),
    ).fetchall()

    overall_series = [{"date": str(r["match_date"]), "value": r["overall_after"]} for r in overall_rows]

    goals_series = []
    assists_series = []
    total_goals = total_assists = 0
    for t in summary["timeline"]:
        total_goals += t["goals"]
        total_assists += t["assists"]
        goals_series.append({"date": t["date"], "value": total_goals})
        assists_series.append({"date": t["date"], "value": total_assists})

    return {"overall": overall_series, "goals": goals_series, "assists": assists_series}


def get_last_delta(db, user_id):
    """Variação do Overall no último jogo confirmado deste jogador (None se ainda não jogou nenhum)."""
    rows = db.execute(
        "SELECT overall_after FROM overall_history WHERE user_id = ? ORDER BY id DESC LIMIT 2",
        (user_id,),
    ).fetchall()
    if not rows:
        return None
    if len(rows) == 1:
        return round(rows[0]["overall_after"] - OVERALL_START, 2)
    return round(rows[0]["overall_after"] - rows[1]["overall_after"], 2)
