from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from database import get_db
from overall_engine import apply_overall_updates
from stats import compute_milestone_bonuses

bp = Blueprint("matches", __name__, url_prefix="/jogos")


def try_confirm_match(db, match_id):
    """Confirma o jogo assim que todos os jogadores tiverem preenchido as suas stats.
    Não valida se a soma dos golos bate certo com o resultado — com um grupo pequeno
    de amigos, cada um mete os seus números de forma sincera.
    Devolve True se ficou (ou já estava) confirmado."""
    match = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if match["status"] == "confirmado":
        return True

    rows = db.execute("SELECT * FROM match_stats WHERE match_id = ?", (match_id,)).fetchall()
    if not rows or not all(r["submitted"] for r in rows):
        return False

    db.execute("UPDATE matches SET status = 'confirmado' WHERE id = ?", (match_id,))
    db.commit()
    bonuses = compute_milestone_bonuses(db, match_id)
    apply_overall_updates(db, match_id, bonus_by_user=bonuses)
    return True


@bp.route("/")
@login_required
def lista():
    db = get_db()
    matches = db.execute(
        "SELECT * FROM matches ORDER BY match_date DESC, id DESC"
    ).fetchall()

    items = []
    for m in matches:
        rows = db.execute(
            """
            SELECT ms.*, u.nickname
            FROM match_stats ms JOIN users u ON u.id = ms.user_id
            WHERE ms.match_id = ?
            """,
            (m["id"],),
        ).fetchall()
        my_row = next((r for r in rows if r["user_id"] == int(current_user.get_id())), None)
        items.append({"match": m, "rows": rows, "my_row": my_row})

    pending_items = [i for i in items if i["match"]["status"] == "pendente"]
    confirmed_items = [i for i in items if i["match"]["status"] == "confirmado"]
    # dentro dos pendentes, os que precisam da minha ação aparecem primeiro
    pending_items.sort(key=lambda i: 0 if (i["my_row"] and not i["my_row"]["submitted"]) else 1)

    return render_template("matches/lista.html", pending_items=pending_items, confirmed_items=confirmed_items)


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY nickname").fetchall()

    if request.method == "POST":
        form = request.form
        match_date = form.get("match_date", "").strip()
        location = form.get("location", "").strip()
        team_a_ids = {int(i) for i in form.getlist("team_a")}
        team_b_ids = {int(i) for i in form.getlist("team_b")}
        team_a_score = form.get("team_a_score", "")
        team_b_score = form.get("team_b_score", "")

        erros = []
        if not match_date:
            erros.append("Escolhe a data do jogo.")
        if not team_a_ids or not team_b_ids:
            erros.append("Cada equipa precisa de pelo menos um jogador.")
        if team_a_ids & team_b_ids:
            erros.append("Um jogador não pode estar nas duas equipas.")
        try:
            team_a_score = int(team_a_score)
            team_b_score = int(team_b_score)
            if team_a_score < 0 or team_b_score < 0:
                raise ValueError
        except ValueError:
            erros.append("O resultado tem de ser um número (0 ou mais) em cada equipa.")
            team_a_score = team_b_score = None

        if erros:
            for erro in erros:
                flash(erro)
            return render_template(
                "matches/novo.html", users=users, form=form,
                team_a_ids=team_a_ids, team_b_ids=team_b_ids,
            ), 400

        cur = db.execute(
            """
            INSERT INTO matches (match_date, location, team_a_score, team_b_score, status, created_by)
            VALUES (?, ?, ?, ?, 'pendente', ?)
            """,
            (match_date, location or None, team_a_score, team_b_score, int(current_user.get_id())),
        )
        match_id = cur.lastrowid

        rows = [(match_id, uid, "A") for uid in team_a_ids] + [(match_id, uid, "B") for uid in team_b_ids]
        db.executemany(
            "INSERT INTO match_stats (match_id, user_id, team) VALUES (?, ?, ?)",
            rows,
        )
        db.commit()

        flash("Jogo criado! Cada jogador já pode preencher as suas stats.")
        return redirect(url_for("matches.detalhe", match_id=match_id))

    return render_template(
        "matches/novo.html", users=users, form={"match_date": date.today().isoformat()},
        team_a_ids=set(), team_b_ids=set(),
    )


@bp.route("/<int:match_id>", methods=["GET", "POST"])
@login_required
def detalhe(match_id):
    db = get_db()
    match = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if match is None:
        abort(404)

    my_id = int(current_user.get_id())
    rows = db.execute(
        """
        SELECT ms.*, u.nickname, u.favorite_player_image_url
        FROM match_stats ms JOIN users u ON u.id = ms.user_id
        WHERE ms.match_id = ?
        """,
        (match_id,),
    ).fetchall()
    my_row = next((r for r in rows if r["user_id"] == my_id), None)
    others = [r for r in rows if r["user_id"] != my_id]

    if request.method == "POST":
        if my_row is None:
            abort(403)
        if match["status"] == "confirmado":
            flash("Este jogo já está confirmado — as stats já não podem ser alteradas.")
            return redirect(url_for("matches.detalhe", match_id=match_id))

        goals = request.form.get("goals", "")
        assists = request.form.get("assists", "")
        mvp_vote_for = request.form.get("mvp_vote_for", "")

        erros = []
        try:
            goals = int(goals)
            assists = int(assists)
            if goals < 0 or assists < 0:
                raise ValueError
        except ValueError:
            erros.append("Golos e assistências têm de ser números (0 ou mais).")
            goals = assists = None

        mvp_vote_for = int(mvp_vote_for) if mvp_vote_for else None
        if mvp_vote_for == my_id:
            erros.append("Não podes votar em ti próprio para MVP.")
        if mvp_vote_for is not None and mvp_vote_for not in {r["user_id"] for r in others}:
            erros.append("Escolhe um MVP entre os outros jogadores deste jogo.")

        if erros:
            for erro in erros:
                flash(erro)
            return redirect(url_for("matches.detalhe", match_id=match_id))

        db.execute(
            """
            UPDATE match_stats
            SET goals = ?, assists = ?, mvp_vote_for = ?, submitted = 1
            WHERE match_id = ? AND user_id = ?
            """,
            (goals, assists, mvp_vote_for, match_id, my_id),
        )
        db.commit()

        confirmed = try_confirm_match(db, match_id)
        flash("Estatísticas guardadas! Jogo confirmado ✅" if confirmed else "Estatísticas guardadas — a aguardar os restantes jogadores.")
        return redirect(url_for("matches.detalhe", match_id=match_id))

    return render_template(
        "matches/detalhe.html",
        match=match, rows=rows, my_row=my_row, others=others,
    )


@bp.route("/<int:match_id>/apagar", methods=["POST"])
@login_required
def apagar(match_id):
    db = get_db()
    match = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if match is None:
        abort(404)

    if match["created_by"] != int(current_user.get_id()):
        abort(403)

    # Confirmed matches are locked: they've already fed the Overall engine,
    # and unwinding that safely would mean recalculating every match after
    # this one (the difficulty multiplier depends on each player's Overall
    # at the time). Simplest and safest is to just not allow it.
    if match["status"] == "confirmado":
        flash("Não é possível apagar um jogo já confirmado.")
        return redirect(url_for("matches.detalhe", match_id=match_id))

    db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    db.commit()
    flash("Jogo apagado.")
    return redirect(url_for("matches.lista"))
