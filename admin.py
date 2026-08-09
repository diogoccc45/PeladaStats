from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

import overall_engine
import stats as stats_mod
from database import delete_user_cascade, get_db
from settings import PES_VALIDOS, _parse_float

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _require_admin():
    if not current_user.is_admin:
        abort(403)


@bp.route("/")
@login_required
def painel():
    _require_admin()
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY nickname").fetchall()
    summaries = stats_mod.get_all_summaries(db)
    matches = db.execute("SELECT * FROM matches ORDER BY match_date DESC, id DESC LIMIT 15").fetchall()

    players = [{"user": u, "games": summaries.get(u["id"], {}).get("games", 0)} for u in users]
    return render_template("admin/painel.html", players=players, matches=matches)


@bp.route("/remover/<int:user_id>", methods=["POST"])
@login_required
def remover(user_id):
    _require_admin()
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    if user_id == int(current_user.get_id()):
        flash("Não podes remover a tua própria conta por aqui.")
        return redirect(url_for("admin.painel"))

    delete_user_cascade(db, user_id)
    flash(f"{user['nickname']} foi removido.")
    return redirect(url_for("admin.painel"))


@bp.route("/jogador/<int:user_id>/promover", methods=["POST"])
@login_required
def promover(user_id):
    _require_admin()
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)

    novo_estado = 0 if user["is_admin"] else 1
    db.execute("UPDATE users SET is_admin = ? WHERE id = ?", (novo_estado, user_id))
    db.commit()
    flash(f"{user['nickname']} agora {'é' if novo_estado else 'deixou de ser'} admin.")
    return redirect(url_for("admin.painel"))


@bp.route("/jogador/<int:user_id>/overall", methods=["POST"])
@login_required
def ajustar_overall(user_id):
    _require_admin()
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)

    novo_overall = _parse_float(
        request.form.get("novo_overall"), user["overall"], overall_engine.OVERALL_MIN, overall_engine.OVERALL_MAX
    )
    db.execute("UPDATE users SET overall = ? WHERE id = ?", (novo_overall, user_id))
    db.execute(
        "INSERT INTO overall_history (user_id, match_id, overall_after) VALUES (?, NULL, ?)",
        (user_id, novo_overall),
    )
    db.commit()
    flash(f"Overall de {user['nickname']} ajustado para {novo_overall}.")
    return redirect(url_for("admin.painel"))


@bp.route("/jogador/<int:user_id>/editar", methods=["GET", "POST"])
@login_required
def editar_jogador(user_id):
    _require_admin()
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)

    if request.method == "POST":
        form = request.form
        nickname = form.get("nickname", "").strip()
        foot = form.get("foot", "").strip().lower()
        fav_player = form.get("favPlayer", "").strip()
        fav_player_img = form.get("favPlayerImg", "").strip()
        fav_team = form.get("favTeam", "").strip()
        fav_team_logo = form.get("favTeamLogo", "").strip()

        player_zoom = _parse_float(form.get("favPlayerImgZoom"), 1.0, 1.0, 3.0)
        player_x = _parse_float(form.get("favPlayerImgPosX"), 50, 0, 100)
        player_y = _parse_float(form.get("favPlayerImgPosY"), 50, 0, 100)
        team_zoom = _parse_float(form.get("favTeamLogoZoom"), 1.0, 1.0, 3.0)
        team_x = _parse_float(form.get("favTeamLogoPosX"), 50, 0, 100)
        team_y = _parse_float(form.get("favTeamLogoPosY"), 50, 0, 100)

        erros = []
        if len(nickname) < 2:
            erros.append("A alcunha tem de ter pelo menos 2 caracteres.")
        if foot not in PES_VALIDOS:
            erros.append("Escolhe o pé preferido.")

        if erros:
            for erro in erros:
                flash(erro)
        else:
            db.execute(
                """
                UPDATE users SET
                    nickname = ?, preferred_foot = ?, favorite_player_name = ?,
                    favorite_player_image_url = ?, favorite_player_image_zoom = ?,
                    favorite_player_image_pos_x = ?, favorite_player_image_pos_y = ?,
                    favorite_team_name = ?, favorite_team_logo_url = ?,
                    favorite_team_logo_zoom = ?, favorite_team_logo_pos_x = ?, favorite_team_logo_pos_y = ?
                WHERE id = ?
                """,
                (
                    nickname, foot, fav_player or None,
                    fav_player_img or None, player_zoom, player_x, player_y,
                    fav_team or None, fav_team_logo or None,
                    team_zoom, team_x, team_y,
                    user_id,
                ),
            )
            db.commit()
            flash(f"Perfil de {nickname} atualizado.")
            return redirect(url_for("admin.painel"))

    return render_template("admin/editar_jogador.html", user=user)


@bp.route("/jogo/<int:match_id>/editar", methods=["GET", "POST"])
@login_required
def editar_jogo(match_id):
    _require_admin()
    db = get_db()
    match = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if match is None:
        abort(404)

    rows = db.execute(
        """
        SELECT ms.*, u.nickname
        FROM match_stats ms JOIN users u ON u.id = ms.user_id
        WHERE ms.match_id = ?
        """,
        (match_id,),
    ).fetchall()
    participant_ids = {r["user_id"] for r in rows}

    if request.method == "POST":
        form = request.form
        erros = []
        updates = []
        for r in rows:
            uid = r["user_id"]
            try:
                goals = int(form.get(f"goals_{uid}", 0))
                assists = int(form.get(f"assists_{uid}", 0))
                if goals < 0 or assists < 0:
                    raise ValueError
            except ValueError:
                erros.append(f"Golos/assistências inválidos para {r['nickname']}.")
                continue

            mvp_raw = form.get(f"mvp_{uid}", "")
            mvp_vote_for = int(mvp_raw) if mvp_raw else None
            if mvp_vote_for == uid:
                erros.append(f"{r['nickname']} não pode votar em si próprio para MVP.")
            elif mvp_vote_for is not None and mvp_vote_for not in participant_ids:
                erros.append(f"Voto de MVP inválido para {r['nickname']}.")

            golo_raw = form.get(f"golo_{uid}", "")
            golo_vote_for = int(golo_raw) if golo_raw else None
            if golo_vote_for == uid:
                erros.append(f"{r['nickname']} não pode votar em si próprio para Golo da Jornada.")
            elif golo_vote_for is not None and golo_vote_for not in participant_ids:
                erros.append(f"Voto de Golo da Jornada inválido para {r['nickname']}.")

            updates.append((goals, assists, mvp_vote_for, golo_vote_for, uid))

        if erros:
            for erro in erros:
                flash(erro)
            return redirect(url_for("admin.editar_jogo", match_id=match_id))

        for goals, assists, mvp_vote_for, golo_vote_for, uid in updates:
            db.execute(
                """
                UPDATE match_stats
                SET goals = ?, assists = ?, mvp_vote_for = ?, goal_of_match_vote_for = ?, submitted = 1
                WHERE match_id = ? AND user_id = ?
                """,
                (goals, assists, mvp_vote_for, golo_vote_for, match_id, uid),
            )
        db.commit()

        if match["status"] == "confirmado":
            stats_mod.recompute_all_overall(db)
            flash("Jogo corrigido — o Overall de todos os jogadores foi recalculado do zero para refletir a correção.")
        else:
            flash("Jogo corrigido.")
        return redirect(url_for("matches.detalhe", match_id=match_id))

    return render_template("admin/editar_jogo.html", match=match, rows=rows)
