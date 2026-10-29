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

# Streak-type achievements are measured over the player's OWN games, in order
# (games he skipped don't break or extend a streak).
FIRE_STREAK_GAMES = 4    # "Em chamas": this many games in a row with at least 1 goal
DROUGHT_GAMES = 4        # "Seca": this many games in a row without scoring
CARRY_MIN_GOALS = 3      # "Carregou a equipa": at least this many goals...
CARRY_TEAM_SHARE = 0.5   # ...and at least this share of his team's goals

# Per-achievement extras:
#   desc        — one-liner shown when the player taps the achievement
#   count_field — also show how many times it has happened (summary field)
#   no_bonus    — unlocking it does NOT give the RECORD_BONUS to Overall
#   secret      — hidden from the list until it's unlocked
# Counter achievements (Golo da Jornada, Em chamas, ...) only pay the Overall
# bonus the FIRST time they unlock — repeats just raise the counter.
ACHIEVEMENTS = [
    {"id": "primeiro_golo", "label": "Primeiro golo", "icon": "⚽", "desc": "Marca o teu primeiro golo.", "check": lambda s: s["goals"] >= 1},
    {"id": "primeira_assistencia", "label": "Primeira assistência", "icon": "🎯", "desc": "Faz a tua primeira assistência.", "check": lambda s: s["assists"] >= 1},
    {"id": "primeiro_mvp", "label": "Primeiro MVP", "icon": "⭐", "desc": "Sê eleito MVP de um jogo.", "check": lambda s: s["mvp"] >= 1},
    {"id": "10_golos", "label": "10 golos", "icon": "⚽", "desc": "Chega aos 10 golos.", "check": lambda s: s["goals"] >= 10, "metric": "goals", "threshold": 10},
    {"id": "25_golos", "label": "25 golos", "icon": "⚽", "desc": "Chega aos 25 golos.", "check": lambda s: s["goals"] >= 25, "metric": "goals", "threshold": 25},
    {"id": "50_golos", "label": "50 golos", "icon": "⚽", "desc": "Chega aos 50 golos.", "check": lambda s: s["goals"] >= 50, "metric": "goals", "threshold": 50},
    {"id": "25_assistencias", "label": "25 assistências", "icon": "🎯", "desc": "Chega às 25 assistências.", "check": lambda s: s["assists"] >= 25, "metric": "assists", "threshold": 25},
    {"id": "10_vitorias", "label": "10 vitórias", "icon": "🏆", "desc": "Chega às 10 vitórias.", "check": lambda s: s["wins"] >= 10, "metric": "wins", "threshold": 10},
    {"id": "hat_trick", "label": "Hat-trick", "icon": "🎩", "desc": "Marca 3 golos no mesmo jogo.", "check": lambda s: s["hat_trick"]},
    {"id": "poquer", "label": "Póquer", "icon": "🃏", "desc": "Marca 4 golos no mesmo jogo.", "check": lambda s: s["poker"]},
    {"id": "golo_da_jornada", "label": "Golo da Jornada", "icon": "🎯", "desc": "Vê o teu golo eleito o melhor do jogo. O número mostra quantas vezes.", "check": lambda s: s["golo_da_jornada"] >= 1, "count_field": "golo_da_jornada"},
    {"id": "100_participacoes", "label": "100 participações em golo", "icon": "🔥", "desc": "Chega às 100 participações em golo (golos + assistências).", "check": lambda s: s["goal_involvements"] >= 100, "metric": "goal_involvements", "threshold": 100},
    {"id": "em_chamas", "label": "Em chamas", "icon": "☄️", "desc": f"Marca em {FIRE_STREAK_GAMES} jogos seguidos. O número mostra quantas sequências já fizeste.", "check": lambda s: s["em_chamas"] >= 1, "count_field": "em_chamas"},
    {"id": "carregou_equipa", "label": "Carregou a equipa", "icon": "💪", "desc": f"Marca {CARRY_MIN_GOALS} ou mais golos e pelo menos metade dos golos da tua equipa num jogo. O número mostra quantas vezes.", "check": lambda s: s["carregou_equipa"] >= 1, "count_field": "carregou_equipa"},
    {"id": "50_jogos", "label": "50 jogos", "icon": "🎖️", "desc": "Disputa 50 jogos.", "check": lambda s: s["games"] >= 50, "metric": "games", "threshold": 50},
    {"id": "100_jogos", "label": "100 jogos", "icon": "💯", "desc": "Disputa 100 jogos.", "check": lambda s: s["games"] >= 100, "metric": "games", "threshold": 100},
    {"id": "seca", "label": "Seca", "icon": "🌵", "desc": f"{DROUGHT_GAMES} jogos seguidos sem marcar. Não conta para o Overall. O número mostra quantas secas já tiveste.", "check": lambda s: s["seca"] >= 1, "count_field": "seca", "no_bonus": True, "secret": True},
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


def count_runs(items, predicate, min_len):
    """How many separate runs of at least min_len consecutive items satisfy
    predicate. A run that keeps going past min_len still counts once."""
    runs = cur = 0
    for it in items:
        if predicate(it):
            cur += 1
            if cur == min_len:
                runs += 1
        else:
            cur = 0
    return runs


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
CHEMISTRY_MIN_GAMES = 3  # games together needed before we call a pair's chemistry strong/weak
CHEMISTRY_DELTA = 10     # win% points above/below the pair's own average that counts as strong/weak
PER_GAME_AVG_WINDOW = 5  # games in the profile chart's moving average (same window as Form)


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
                "team_goals": m["team_a_score"] if row["team"] == "A" else m["team_b_score"],
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
        "em_chamas": count_runs(timeline, lambda t: t["goals"] >= 1, FIRE_STREAK_GAMES),
        "seca": count_runs(timeline, lambda t: t["goals"] == 0, DROUGHT_GAMES),
        "carregou_equipa": sum(
            1 for t in timeline
            if t["goals"] >= CARRY_MIN_GOALS and t["goals"] >= CARRY_TEAM_SHARE * t["team_goals"]
        ),
        "timeline": timeline,
    }
    summary["form"] = compute_form(timeline)
    return summary


def _win_pct(wins, games):
    return round(100 * wins / games) if games else None


def get_pair_chemistry(db, a_id, b_id, summary_a=None, summary_b=None):
    """How two players do TOGETHER (same team) and AGAINST each other, from
    every confirmed match both played. For the verdict, the win% together is
    compared with the average of the two players' overall win% (a pair that
    wins clearly more often than they each normally do has good chemistry)."""
    together = {"games": 0, "wins": 0, "draws": 0, "losses": 0, "goals_for": 0, "goals_against": 0}
    against = {"games": 0, "a_wins": 0, "draws": 0, "b_wins": 0}

    for m, rows in get_confirmed_matches_with_stats(db):
        ra = next((r for r in rows if r["user_id"] == a_id and r["submitted"]), None)
        rb = next((r for r in rows if r["user_id"] == b_id and r["submitted"]), None)
        if ra is None or rb is None:
            continue
        result_a = _result_for(ra, m)
        if ra["team"] == rb["team"]:
            together["games"] += 1
            together[{"win": "wins", "draw": "draws", "loss": "losses"}[result_a]] += 1
            mine, theirs = (m["team_a_score"], m["team_b_score"]) if ra["team"] == "A" else (m["team_b_score"], m["team_a_score"])
            together["goals_for"] += mine
            together["goals_against"] += theirs
        else:
            against["games"] += 1
            against[{"win": "a_wins", "draw": "draws", "loss": "b_wins"}[result_a]] += 1

    games = together["games"]
    together["win_pct"] = _win_pct(together["wins"], games)
    together["avg_for"] = round(together["goals_for"] / games, 1) if games else None
    together["avg_against"] = round(together["goals_against"] / games, 1) if games else None

    baseline_pcts = [
        _win_pct(sm["wins"], sm["games"]) for sm in (summary_a, summary_b) if sm and sm["games"]
    ]
    baseline = round(sum(baseline_pcts) / len(baseline_pcts)) if baseline_pcts else None

    if games == 0:
        verdict = None
    elif games < CHEMISTRY_MIN_GAMES or baseline is None:
        verdict = {"emoji": "🤷", "label": "Poucos jogos juntos para tirar conclusões"}
    elif together["win_pct"] - baseline >= CHEMISTRY_DELTA:
        verdict = {"emoji": "🔥", "label": "Química forte — ganham mais juntos do que sozinhos"}
    elif together["win_pct"] - baseline <= -CHEMISTRY_DELTA:
        verdict = {"emoji": "🧊", "label": "Química fraca — ganham menos juntos do que sozinhos"}
    else:
        verdict = {"emoji": "⚖️", "label": "Na média — juntos rendem como rendem sozinhos"}

    return {"together": together, "against": against, "baseline_pct": baseline, "verdict": verdict}


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
        unlocked = bool(a["check"](summary))
        if a.get("secret") and not unlocked:
            continue  # secret achievements stay hidden until earned
        entry = {
            "id": a["id"], "label": a["label"], "icon": a["icon"], "desc": a.get("desc", ""),
            "unlocked": unlocked, "no_bonus": bool(a.get("no_bonus")),
        }
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


def get_rank_movement(db, match_id=None):
    """Leaderboard positions right before and right after one match (default:
    the most recently confirmed one), rebuilt from overall_history so it
    needs no extra stored data. change[user_id] > 0 means the player climbed
    that many places; < 0 means they dropped.

    Everyone who has no history yet counts at OVERALL_START, same as the live
    ranking (get_rank) — that keeps the "before" and "after" lists made of
    the same people, so the comparison is fair."""
    if match_id is None:
        row = db.execute(
            "SELECT match_id FROM overall_history WHERE match_id IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        match_id = row["match_id"]

    bounds = db.execute(
        "SELECT MIN(id) lo, MAX(id) hi FROM overall_history WHERE match_id = ?", (match_id,)
    ).fetchone()
    if bounds["lo"] is None:
        return None

    user_ids = [r["id"] for r in db.execute("SELECT id FROM users")]

    def snapshot(op, history_id):
        rows = db.execute(
            f"""
            SELECT user_id, overall_after FROM overall_history
            WHERE id IN (SELECT MAX(id) FROM overall_history WHERE id {op} ? GROUP BY user_id)
            """,
            (history_id,),
        ).fetchall()
        return {r["user_id"]: r["overall_after"] for r in rows}

    values_before = snapshot("<", bounds["lo"])
    values_after = snapshot("<=", bounds["hi"])

    def ranks(values):
        order = sorted(user_ids, key=lambda u: (-values.get(u, OVERALL_START), u))
        return {u: i + 1 for i, u in enumerate(order)}

    rank_before, rank_after = ranks(values_before), ranks(values_after)
    return {
        "match_id": match_id,
        "rank_before": rank_before,
        "rank_after": rank_after,
        "change": {u: rank_before[u] - rank_after[u] for u in user_ids},
        "overall_before": values_before,
        "overall_after": values_after,
    }


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
    top_golo_da_jornada_season = {"value": 0, "user_id": None}

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
        if s["golo_da_jornada"] > top_golo_da_jornada_season["value"]:
            top_golo_da_jornada_season = {"value": s["golo_da_jornada"], "user_id": uid}

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
        "top_golo_da_jornada_season": leaderboard({uid: s["golo_da_jornada"] for uid, s in summaries.items()}),
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
        "top_golo_da_jornada_season": top_golo_da_jornada_season,
        "leaderboards": leaderboards,
        "users": users,
    }


# Record categories eligible for the milestone Overall bonus — deliberately
# excludes loss_streak (nothing to reward there) and the season-cumulative
# leaderboards (those would re-trigger for the current leader almost every
# time they play, which doesn't fit the "special one-off milestone" spirit).
BONUS_ELIGIBLE_RECORDS = ("best_goals", "best_assists", "best_involvement", "win_streak", "mvp_streak", "most_games")

RECORD_LABELS = {
    "best_goals": "Recorde: Mais golos num jogo",
    "best_assists": "Recorde: Mais assistências num jogo",
    "best_involvement": "Recorde: Mais participações num jogo",
    "win_streak": "Recorde: Maior sequência de vitórias",
    "mvp_streak": "Recorde: Mais MVP consecutivos",
    "most_games": "Recorde: Mais jogos disputados",
}


def _detect_unlocks(db, match_id, up_to=None):
    """[{"user_id", "label"}, ...] for every record or achievement newly
    unlocked because of this specific match. Compares a "before this match"
    snapshot against the current ("after") state.

    Shared by compute_milestone_bonuses (sums RECORD_BONUS per user) and
    create_unlock_notifications (writes one row per unlock) so the detection
    logic — and the up_to point-in-time guard needed for a safe recompute
    replay — only lives in one place.

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

    unlocks = []

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
            unlocks.append({
                "user_id": after["user_id"], "label": RECORD_LABELS[key],
                "kind": "record", "icon": "📈", "no_bonus": False,
            })

    # Achievements: anyone in this match who crossed from locked to unlocked
    # on any achievement, purely because of this match.
    for user_id in participant_ids:
        summary_before = get_player_summary(db, user_id, exclude_match_id=match_id, up_to=up_to)
        summary_after = get_player_summary(db, user_id, up_to=up_to)
        unlocked_before = {a["id"] for a in get_achievements(summary_before) if a["unlocked"]}
        for a in get_achievements(summary_after):
            if a["unlocked"] and a["id"] not in unlocked_before:
                unlocks.append({
                    "user_id": user_id, "label": a["label"], "kind": "achievement",
                    "icon": a["icon"], "desc": a["desc"], "no_bonus": a["no_bonus"],
                })

    return unlocks


def compute_milestone_bonuses(db, match_id, up_to=None):
    """{user_id: bonus_total} for players who, because of this specific match,
    either set a new global record or unlocked a new achievement."""
    bonuses = {}
    for u in _detect_unlocks(db, match_id, up_to=up_to):
        if u["no_bonus"]:
            continue
        bonuses[u["user_id"]] = bonuses.get(u["user_id"], 0) + RECORD_BONUS
    return bonuses


def create_unlock_notifications(db, match_id):
    """Writes one notifications row per record/achievement newly unlocked by
    this match, for whoever unlocked it — regardless of whether that player
    is the one whose submission happened to confirm the match. Only called
    from the normal single-match confirmation flow (matches.py), never
    during recompute_all_overall's replay — an admin correcting an old match
    shouldn't flood everyone with notifications for things they unlocked
    long ago."""
    from push import send_push_to_user

    unlocks = _detect_unlocks(db, match_id)
    celebrated = [u for u in unlocks if not u["no_bonus"]]
    gags = [u for u in unlocks if u["no_bonus"]]  # e.g. Seca: tell them, but don't celebrate

    for u in celebrated:
        db.execute(
            "INSERT INTO notifications (user_id, label, match_id) VALUES (?, ?, ?)",
            (u["user_id"], u["label"], match_id),
        )
    for u in gags:
        db.execute(
            "INSERT INTO notifications (user_id, kind, label, match_id) VALUES (?, 'reminder', ?, ?)",
            (u["user_id"], f"{u['icon']} {u['label']}: {u['desc'].split('. ')[0].rstrip('.')}", match_id),
        )
    if unlocks:
        db.commit()
        # Um único push por jogador, mesmo que tenha desbloqueado várias
        # coisas no mesmo jogo (comum no primeiro jogo de alguém) — cada
        # desbloqueio continua a aparecer como linha própria no sino.
        by_user = {}
        for u in celebrated:
            by_user.setdefault(u["user_id"], []).append(u["label"])
        for user_id, labels in by_user.items():
            title = "🏆 Conquista desbloqueada!" if len(labels) == 1 else "🏆 Conquistas desbloqueadas!"
            send_push_to_user(user_id, title, " · ".join(labels))
        for u in gags:
            send_push_to_user(u["user_id"], f"{u['icon']} {u['label']}", u["desc"].split(". ")[0].rstrip("."))
    return unlocks


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

    # One point per game the player actually played (never the group's other
    # matches). "value" is the running total; "game" is that match alone and
    # "avg" the moving average of the last PER_GAME_AVG_WINDOW games (fewer at
    # the start of the season) — the profile can show either view.
    goals_series = []
    assists_series = []
    total_goals = total_assists = 0
    recent_goals = []
    recent_assists = []
    for t in summary["timeline"]:
        total_goals += t["goals"]
        total_assists += t["assists"]
        recent_goals = (recent_goals + [t["goals"]])[-PER_GAME_AVG_WINDOW:]
        recent_assists = (recent_assists + [t["assists"]])[-PER_GAME_AVG_WINDOW:]
        goals_series.append({
            "date": t["date"], "value": total_goals, "game": t["goals"],
            "avg": round(sum(recent_goals) / len(recent_goals), 2),
        })
        assists_series.append({
            "date": t["date"], "value": total_assists, "game": t["assists"],
            "avg": round(sum(recent_assists) / len(recent_assists), 2),
        })

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
