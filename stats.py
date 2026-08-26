"""
Cálculos partilhados entre o dashboard, o perfil, os recordes e a comparação.

Tudo parte de get_confirmed_matches_with_stats(): a lista de jogos confirmados,
cada um com as respetivas linhas de match_stats. A partir daí construímos, por
jogador, uma "timeline" cronológica (resultado, golos, assistências, se foi MVP
nesse jogo) que serve de base a tudo o resto — forma, streaks para recordes, e
as séries dos gráficos de evolução.
"""

from overall_engine import OVERALL_START, compute_goal_of_match_winners, compute_match_mvps

FORM_LEVELS = [
    (0.8, "Excelente", "🔥"),
    (0.6, "Boa", "🟢"),
    (0.4, "Normal", "🟡"),
    (0.2, "Fraca", "🟠"),
    (0.0, "Péssima", "🔴"),
]

# Extra Overall points awarded once, the match a player sets a new global
# record (Recordes page) or unlocks a new achievement — a flat, unscaled
# bonus, same spirit as the match-result penalties: always full strength.
RECORD_BONUS = 0.1

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
    {"id": "poquer", "label": "Póquer", "icon": "🃏", "check": lambda s: s["poker"]},
    {"id": "golo_da_jornada", "label": "Golo da Jornada", "icon": "🎯", "check": lambda s: s["golo_da_jornada"] >= 1, "count_field": "golo_da_jornada"},
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


def get_confirmed_matches_with_stats(db, exclude_match_id=None, up_to=None):
    """[(match_row, [match_stats_rows]), ...] ordenado do jogo mais antigo para o mais recente.
    exclude_match_id deixa de fora um jogo específico — usado para comparar o
    "antes" e o "depois" de um jogo em concreto (recordes/conquistas novas).
    up_to (match_date, id) só inclui jogos até esse ponto no tempo (inclusive)
    — usado durante um recálculo completo do Overall, para que cada passo do
    replay só "veja" o que já tinha acontecido nessa altura, não jogos futuros
    que já estejam confirmados na base de dados."""
    matches = db.execute(
        "SELECT * FROM matches WHERE status = 'confirmado' ORDER BY match_date ASC, id ASC"
    ).fetchall()
    out = []
    for m in matches:
        if exclude_match_id is not None and m["id"] == exclude_match_id:
            continue
        if up_to is not None and (str(m["match_date"]), m["id"]) > up_to:
            continue
        rows = db.execute("SELECT * FROM match_stats WHERE match_id = ?", (m["id"],)).fetchall()
        out.append((m, rows))
    return out


def compute_match_mvp_map(matches_with_stats):
    """{match_id: {user_id que foi MVP nesse jogo}}"""
    return {m["id"]: compute_match_mvps(rows) for m, rows in matches_with_stats}


def compute_match_golo_map(matches_with_stats):
    """{match_id: {user_id que marcou o Golo da Jornada nesse jogo}}"""
    return {m["id"]: compute_goal_of_match_winners(rows) for m, rows in matches_with_stats}


def longest_streak(items, predicate):
    best = cur = 0
    for it in items:
        if predicate(it):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


FORM_CONFIDENCE_GAMES = 5  # jogos recentes necessários para "confiança total" na forma
FORM_RESULT_WEIGHT = 0.6
FORM_CONTRIBUTION_WEIGHT = 0.4
FORM_GOAL_WEIGHT = 0.25
FORM_ASSIST_WEIGHT = 0.15
FORM_MVP_WEIGHT = 0.35


def compute_form(timeline):
    """Forma = mistura de resultado (60%) e exibição individual (40%,
    golos+assistências+MVP, com um teto por jogo) nos últimos 5 jogos.

    Com poucos jogos recentes, uma leitura de "forma" (que é sobre tendência)
    não é fiável — por isso o resultado é puxado para "Normal" (0.5)
    proporcionalmente à falta de jogos: com 1 jogo em 5, só 20% do peso vai
    para o que realmente aconteceu nesse jogo; com 5 jogos, 100%."""
    recent = timeline[-5:]
    if not recent:
        return {"label": "Sem jogos", "emoji": "⚪", "ratio": None}

    game_scores = []
    for g in recent:
        if g["result"] == "win":
            result_component = 1.0
        elif g["result"] == "draw":
            result_component = 0.5
        else:
            result_component = 0.0
        contribution_component = min(
            1.0,
            g["goals"] * FORM_GOAL_WEIGHT + g["assists"] * FORM_ASSIST_WEIGHT + (FORM_MVP_WEIGHT if g["was_mvp"] else 0),
        )
        game_scores.append(FORM_RESULT_WEIGHT * result_component + FORM_CONTRIBUTION_WEIGHT * contribution_component)

    raw_ratio = sum(game_scores) / len(game_scores)
    confidence = len(recent) / FORM_CONFIDENCE_GAMES
    ratio = 0.5 + confidence * (raw_ratio - 0.5)

    for threshold, label, emoji in FORM_LEVELS:
        if ratio >= threshold:
            return {"label": label, "emoji": emoji, "ratio": ratio}
    return {"label": "Péssima", "emoji": "🔴", "ratio": ratio}


def summarize_user(user_id, matches_with_stats, mvp_map, golo_map):
    games = wins = losses = draws = goals = assists = mvp_count = golo_count = 0
    timeline = []

    for m, rows in matches_with_stats:
        row = next((r for r in rows if r["user_id"] == user_id), None)
        if row is None or not row["submitted"]:
            continue
        result = _result_for(row, m)
        was_mvp = user_id in mvp_map.get(m["id"], set())
        was_golo = user_id in golo_map.get(m["id"], set())

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
        if was_golo:
            golo_count += 1

        timeline.append(
            {
                "match_id": m["id"],
                "date": str(m["match_date"]),
                "location": m["location"],
                "result": result,
                "goals": row["goals"],
                "assists": row["assists"],
                "was_mvp": was_mvp,
                "was_golo_da_jornada": was_golo,
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
        "golo_da_jornada": golo_count,
        "goal_involvements": goal_involvements,
        "avg_goals": (goals / games) if games else 0,
        "avg_assists": (assists / games) if games else 0,
        "hat_trick": any(t["goals"] >= 3 for t in timeline),
        "poker": any(t["goals"] >= 4 for t in timeline),
        "timeline": timeline,
    }
    summary["form"] = compute_form(timeline)
    return summary


def get_all_summaries(db, exclude_match_id=None, up_to=None):
    """{user_id: summary} para todos os jogadores, calculado a partir de um único varrimento dos jogos confirmados."""
    matches_with_stats = get_confirmed_matches_with_stats(db, exclude_match_id=exclude_match_id, up_to=up_to)
    mvp_map = compute_match_mvp_map(matches_with_stats)
    golo_map = compute_match_golo_map(matches_with_stats)
    user_ids = [r["id"] for r in db.execute("SELECT id FROM users").fetchall()]
    return {uid: summarize_user(uid, matches_with_stats, mvp_map, golo_map) for uid in user_ids}


def get_player_summary(db, user_id, exclude_match_id=None, up_to=None):
    matches_with_stats = get_confirmed_matches_with_stats(db, exclude_match_id=exclude_match_id, up_to=up_to)
    mvp_map = compute_match_mvp_map(matches_with_stats)
    golo_map = compute_match_golo_map(matches_with_stats)
    return summarize_user(user_id, matches_with_stats, mvp_map, golo_map)


def get_achievements(summary):
    achievements = []
    for a in ACHIEVEMENTS:
        entry = {"id": a["id"], "label": a["label"], "icon": a["icon"], "unlocked": bool(a["check"](summary))}
        if "count_field" in a:
            entry["count"] = summary[a["count_field"]]
        achievements.append(entry)
    return achievements


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


def get_records(db, exclude_match_id=None, up_to=None):
    matches_with_stats = get_confirmed_matches_with_stats(db, exclude_match_id=exclude_match_id, up_to=up_to)
    mvp_map = compute_match_mvp_map(matches_with_stats)
    golo_map = compute_match_golo_map(matches_with_stats)
    users = {r["id"]: r for r in db.execute("SELECT * FROM users").fetchall()}
    summaries = {uid: summarize_user(uid, matches_with_stats, mvp_map, golo_map) for uid in users}

    # Personal bests per user for the single-game categories (needed both for
    # the global record and for the per-category leaderboard popup).
    personal_best_goals = {uid: 0 for uid in users}
    personal_best_assists = {uid: 0 for uid in users}
    personal_best_involvement = {uid: 0 for uid in users}
    best_goals = {"value": 0, "user_id": None, "date": None}
    best_assists = {"value": 0, "user_id": None, "date": None}
    best_involvement = {"value": 0, "user_id": None, "date": None}
    for m, rows in matches_with_stats:
        for r in rows:
            if not r["submitted"]:
                continue
            uid = r["user_id"]
            inv = r["goals"] + r["assists"]
            personal_best_goals[uid] = max(personal_best_goals[uid], r["goals"])
            personal_best_assists[uid] = max(personal_best_assists[uid], r["assists"])
            personal_best_involvement[uid] = max(personal_best_involvement[uid], inv)

            entry_goals = {"value": r["goals"], "user_id": uid, "date": str(m["match_date"])}
            entry_assists = {"value": r["assists"], "user_id": uid, "date": str(m["match_date"])}
            entry_inv = {"value": inv, "user_id": uid, "date": str(m["match_date"])}
            if entry_goals["value"] > best_goals["value"]:
                best_goals = entry_goals
            if entry_assists["value"] > best_assists["value"]:
                best_assists = entry_assists
            if entry_inv["value"] > best_involvement["value"]:
                best_involvement = entry_inv

    win_streak = {"value": 0, "user_id": None}
    loss_streak = {"value": 0, "user_id": None}
    mvp_streak = {"value": 0, "user_id": None}
    most_games = {"value": 0, "user_id": None}
    top_goals_season = {"value": 0, "user_id": None}
    top_assists_season = {"value": 0, "user_id": None}
    top_involvement_season = {"value": 0, "user_id": None}
    top_mvp_season = {"value": 0, "user_id": None}

    personal_win_streak = {}
    personal_loss_streak = {}
    personal_mvp_streak = {}

    for uid, s in summaries.items():
        w = longest_streak(s["timeline"], lambda t: t["result"] == "win")
        l = longest_streak(s["timeline"], lambda t: t["result"] == "loss")
        mv = longest_streak(s["timeline"], lambda t: t["was_mvp"])
        personal_win_streak[uid] = w
        personal_loss_streak[uid] = l
        personal_mvp_streak[uid] = mv

        if w > win_streak["value"]:
            win_streak = {"value": w, "user_id": uid}
        if l > loss_streak["value"]:
            loss_streak = {"value": l, "user_id": uid}
        if mv > mvp_streak["value"]:
            mvp_streak = {"value": mv, "user_id": uid}
        if s["games"] > most_games["value"]:
            most_games = {"value": s["games"], "user_id": uid}
        if s["goals"] > top_goals_season["value"]:
            top_goals_season = {"value": s["goals"], "user_id": uid}
        if s["assists"] > top_assists_season["value"]:
            top_assists_season = {"value": s["assists"], "user_id": uid}
        if s["goal_involvements"] > top_involvement_season["value"]:
            top_involvement_season = {"value": s["goal_involvements"], "user_id": uid}
        if s["mvp"] > top_mvp_season["value"]:
            top_mvp_season = {"value": s["mvp"], "user_id": uid}

    def leaderboard(values_by_user):
        rows = [
            {"user_id": uid, "nickname": users[uid]["nickname"], "value": v}
            for uid, v in values_by_user.items()
            if uid in users
        ]
        rows.sort(key=lambda r: r["value"], reverse=True)
        return rows

    leaderboards = {
        "best_goals": leaderboard(personal_best_goals),
        "best_assists": leaderboard(personal_best_assists),
        "best_involvement": leaderboard(personal_best_involvement),
        "win_streak": leaderboard(personal_win_streak),
        "loss_streak": leaderboard(personal_loss_streak),
        "mvp_streak": leaderboard(personal_mvp_streak),
        "most_games": leaderboard({uid: s["games"] for uid, s in summaries.items()}),
        "top_goals_season": leaderboard({uid: s["goals"] for uid, s in summaries.items()}),
        "top_assists_season": leaderboard({uid: s["assists"] for uid, s in summaries.items()}),
        "top_involvement_season": leaderboard({uid: s["goal_involvements"] for uid, s in summaries.items()}),
        "top_mvp_season": leaderboard({uid: s["mvp"] for uid, s in summaries.items()}),
    }

    return {
        "best_goals": best_goals,
        "best_assists": best_assists,
        "best_involvement": best_involvement,
        "win_streak": win_streak,
        "loss_streak": loss_streak,
        "mvp_streak": mvp_streak,
        "most_games": most_games,
        "top_goals_season": top_goals_season,
        "top_assists_season": top_assists_season,
        "top_involvement_season": top_involvement_season,
        "top_mvp_season": top_mvp_season,
        "leaderboards": leaderboards,
        "users": users,
    }


# Record categories eligible for the milestone Overall bonus — deliberately
# excludes loss_streak (nothing to reward there) and the season-cumulative
# leaderboards (those would re-trigger for the current leader almost every
# time they play, which doesn't fit the "special one-off milestone" spirit).
BONUS_ELIGIBLE_RECORDS = ("best_goals", "best_assists", "best_involvement", "win_streak", "mvp_streak", "most_games")


def compute_milestone_bonuses(db, match_id, up_to=None):
    """{user_id: bonus_total} for players who, because of this specific match,
    either set a new global record or unlocked a new achievement. Compares a
    "before this match" snapshot against the current ("after") state.

    up_to: see get_confirmed_matches_with_stats — defaults to this match's own
    (date, id), i.e. "as of right now". Passed explicitly during a full replay
    (recompute_all_overall) so a later admin correction doesn't leak future
    matches into an earlier step's "before/after" comparison."""
    match = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if up_to is None:
        up_to = (str(match["match_date"]), match_id)

    participant_ids = {
        r["user_id"] for r in db.execute("SELECT user_id FROM match_stats WHERE match_id = ?", (match_id,))
    }

    bonuses = {}

    # Records: did the holder of any bonus-eligible category change, and is
    # the new holder someone who played in this match?
    records_before = get_records(db, exclude_match_id=match_id, up_to=up_to)
    records_after = get_records(db, up_to=up_to)
    for key in BONUS_ELIGIBLE_RECORDS:
        before = records_before[key]
        after = records_after[key]
        if (after["value"], after["user_id"]) == (before["value"], before["user_id"]):
            continue
        if after["user_id"] in participant_ids:
            bonuses[after["user_id"]] = bonuses.get(after["user_id"], 0) + RECORD_BONUS

    # Achievements: anyone in this match who crossed from locked to unlocked
    # on any achievement, purely because of this match.
    for user_id in participant_ids:
        summary_before = get_player_summary(db, user_id, exclude_match_id=match_id, up_to=up_to)
        summary_after = get_player_summary(db, user_id, up_to=up_to)
        unlocked_before = {a["id"] for a in get_achievements(summary_before) if a["unlocked"]}
        unlocked_after = {a["id"] for a in get_achievements(summary_after) if a["unlocked"]}
        newly_unlocked = unlocked_after - unlocked_before
        if newly_unlocked:
            bonuses[user_id] = bonuses.get(user_id, 0) + RECORD_BONUS * len(newly_unlocked)

    return bonuses


def recompute_all_overall(db):
    """Resets every player's Overall to the start and replays every confirmed
    match, oldest first, from scratch — recomputing base deltas AND milestone
    bonuses at each step exactly as they'd have happened live. Used after an
    admin correction to a confirmed match's stats, so the fix propagates
    properly instead of leaving the rest of the history stale."""
    from overall_engine import OVERALL_START, apply_overall_updates

    db.execute("DELETE FROM overall_history")
    db.execute("UPDATE users SET overall = ?", (OVERALL_START,))
    db.commit()

    matches = db.execute(
        "SELECT id, match_date FROM matches WHERE status = 'confirmado' ORDER BY match_date ASC, id ASC"
    ).fetchall()
    for m in matches:
        up_to = (str(m["match_date"]), m["id"])
        bonuses = compute_milestone_bonuses(db, m["id"], up_to=up_to)
        apply_overall_updates(db, m["id"], bonus_by_user=bonuses)


def get_evolution_series(db, user_id, summary):
    overall_rows = db.execute(
        """
        SELECT oh.overall_after, COALESCE(m.match_date, date(oh.recorded_at)) AS event_date
        FROM overall_history oh
        LEFT JOIN matches m ON m.id = oh.match_id
        WHERE oh.user_id = ?
        ORDER BY event_date ASC, oh.id ASC
        """,
        (user_id,),
    ).fetchall()

    overall_series = [{"date": str(r["event_date"]), "value": r["overall_after"]} for r in overall_rows]

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
