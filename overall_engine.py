"""
Overall rating engine.
  - Roughly doubles/triples the weight of match RESULT (win/loss) relative
    to individual stats, so playing for the team win matters more than
    chasing personal numbers.
  - Raises the minimum floor, since losses now hurt more.
  - Adds a milestone bonus (see RECORD_BONUS) for setting a new global
    record or unlocking a new achievement, on top of the normal per-match
    deltas — handled in stats.compute_milestone_bonuses(), passed in here
    as bonus_by_user so this module doesn't need to import stats.py (would
    be a circular import — stats.py already imports from this module).
  - A blowout penalty: losing by more than BLOWOUT_THRESHOLD goals costs a
    little extra, and the extra cost grows with the margin.
  - Golo da Jornada: like the MVP vote, but for the prettiest goal of the
    match. Small bonus, same empates-do-nada-a-ninguém rule as MVP.

Positivas, por jogador, por jogo:
    Vitória:         +0.40
    Golo:            +0.15 x golos marcados
    Assistência:     +0.12 x assistências
    MVP do jogo:     +0.30  (mais votos; empates -> ninguém recebe o bónus)
    Golo da Jornada: +0.10  (mesma regra de empate que o MVP)

Negativas:
    Derrota:                          -0.35
    Sem golo nem assistência no jogo: -0.15
    Zero votos de MVP no jogo:        -0.05
    Goleada sofrida (perder por mais de 5 golos):
        -0.05 por cada golo de diferença acima de 5
        (perder por 6 = -0.05, por 7 = -0.10, por 8 = -0.15, ...)

Dificuldade progressiva (aplicada ao TOTAL DAS POSITIVAS, com base no Overall
ANTES do jogo). As negativas aplicam-se sempre a 100% — não faria sentido um
jogador em alta ter as suas más exibições "protegidas" pelo multiplicador:
    50-70  -> x1.20
    71-80  -> x1.00
    81-85  -> x0.80
    86-90  -> x0.60
    91-95  -> x0.40
    96-99  -> x0.20

Overall final fica sempre entre 55 e 99.
"""

from collections import Counter

OVERALL_MIN = 55
OVERALL_MAX = 99
OVERALL_START = 65

WIN_BONUS = 0.40
GOAL_BONUS = 0.15
ASSIST_BONUS = 0.12
MVP_BONUS = 0.30
GOAL_OF_MATCH_BONUS = 0.10

LOSS_PENALTY = -0.35
QUIET_GAME_PENALTY = -0.15
ZERO_VOTES_PENALTY = -0.05

BLOWOUT_THRESHOLD = 5
BLOWOUT_STEP = -0.05


def difficulty_multiplier(overall_before):
    if overall_before <= 70:
        return 1.20
    if overall_before <= 80:
        return 1.00
    if overall_before <= 85:
        return 0.80
    if overall_before <= 90:
        return 0.60
    if overall_before <= 95:
        return 0.40
    return 0.20


def _match_result(team, team_a_score, team_b_score):
    if team_a_score == team_b_score:
        return "draw"
    if (team == "A" and team_a_score > team_b_score) or (team == "B" and team_b_score > team_a_score):
        return "win"
    return "loss"


def blowout_penalty(result, team_a_score, team_b_score):
    """Extra penalty for losing by more than BLOWOUT_THRESHOLD goals — grows
    by BLOWOUT_STEP for every goal of margin beyond the threshold."""
    if result != "loss":
        return 0.0
    margin = abs(team_a_score - team_b_score)
    if margin <= BLOWOUT_THRESHOLD:
        return 0.0
    return (margin - BLOWOUT_THRESHOLD) * BLOWOUT_STEP


def _top_unique_voted(stat_rows, vote_field):
    """Shared logic for both MVP and Golo da Jornada: whoever has the most
    votes in vote_field, only if that top count is uniquely held — a tie at
    the top means nobody gets the bonus."""
    votes = Counter(r[vote_field] for r in stat_rows if r[vote_field] is not None)
    if not votes:
        return set()
    top = max(votes.values())
    top_scorers = [uid for uid, count in votes.items() if count == top]
    if len(top_scorers) > 1:
        return set()
    return {top_scorers[0]}


def compute_match_mvps(stat_rows):
    """Devolve o conjunto de user_ids que são MVP do jogo (vazio em caso de empate no topo)."""
    return _top_unique_voted(stat_rows, "mvp_vote_for")


def compute_goal_of_match_winners(stat_rows):
    """Devolve o conjunto de user_ids que marcaram o Golo da Jornada (vazio em caso de empate no topo)."""
    return _top_unique_voted(stat_rows, "goal_of_match_vote_for")


def apply_overall_updates(db, match_id, bonus_by_user=None):
    """
    Aplica os deltas de Overall a todos os participantes de um jogo confirmado.
    Grava o novo Overall em users e um registo em overall_history.

    bonus_by_user: {user_id: pontos extra}, opcional — bónus de recorde/conquista
    (RECORD_BONUS, calculado em stats.compute_milestone_bonuses) somado ao
    delta normal, sem multiplicador de dificuldade, antes de aplicar o clamp.

    Devolve uma lista de dicts com o detalhe do cálculo (útil para testes/depuração).
    """
    bonus_by_user = bonus_by_user or {}

    match = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    stat_rows = db.execute(
        "SELECT * FROM match_stats WHERE match_id = ?", (match_id,)
    ).fetchall()

    mvps = compute_match_mvps(stat_rows)
    goal_winners = compute_goal_of_match_winners(stat_rows)
    voted_uids = {r["mvp_vote_for"] for r in stat_rows if r["mvp_vote_for"] is not None}

    results = []
    for row in stat_rows:
        result = _match_result(row["team"], match["team_a_score"], match["team_b_score"])

        positive = 0.0
        negative = 0.0

        if result == "win":
            positive += WIN_BONUS
        elif result == "loss":
            negative += LOSS_PENALTY
            negative += blowout_penalty(result, match["team_a_score"], match["team_b_score"])

        positive += row["goals"] * GOAL_BONUS
        positive += row["assists"] * ASSIST_BONUS

        if row["goals"] == 0 and row["assists"] == 0:
            negative += QUIET_GAME_PENALTY

        if row["user_id"] in mvps:
            positive += MVP_BONUS

        if row["user_id"] in goal_winners:
            positive += GOAL_OF_MATCH_BONUS

        if row["user_id"] not in voted_uids:
            negative += ZERO_VOTES_PENALTY

        user = db.execute("SELECT overall FROM users WHERE id = ?", (row["user_id"],)).fetchone()
        overall_before = user["overall"]
        multiplier = difficulty_multiplier(overall_before)
        bonus = bonus_by_user.get(row["user_id"], 0)
        delta = positive * multiplier + negative + bonus
        overall_after = max(OVERALL_MIN, min(OVERALL_MAX, overall_before + delta))

        db.execute("UPDATE users SET overall = ? WHERE id = ?", (overall_after, row["user_id"]))
        db.execute(
            "INSERT INTO overall_history (user_id, match_id, overall_after) VALUES (?, ?, ?)",
            (row["user_id"], match_id, overall_after),
        )

        results.append(
            {
                "user_id": row["user_id"],
                "result": result,
                "positive": positive,
                "negative": negative,
                "multiplier": multiplier,
                "bonus": bonus,
                "delta": delta,
                "overall_before": overall_before,
                "overall_after": overall_after,
                "was_mvp": row["user_id"] in mvps,
                "was_goal_of_match": row["user_id"] in goal_winners,
            }
        )

    db.commit()
    return results
