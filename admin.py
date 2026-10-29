from datetime import date, datetime

from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

import overall_engine
import stats as stats_mod
from database import delete_user_cascade, get_db
from push import send_push_to_user
from settings import PES_VALIDOS, _parse_float
from xlsx_export import build_stats_workbook
from xlsx_import import ImportError_, import_matches_from_workbook

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
    # The 15 most recent matches, plus every pending one however old — a
    # forgotten pending match is exactly what the admin may want to clean up.
    matches = db.execute(
        """
        SELECT * FROM matches
        WHERE status = 'pendente'
           OR id IN (SELECT id FROM matches ORDER BY match_date DESC, id DESC LIMIT 15)
        ORDER BY match_date DESC, id DESC
        """
    ).fetchall()

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


def _match_participant_ids(db, match_id):
    return [r["user_id"] for r in db.execute("SELECT user_id FROM match_stats WHERE match_id = ?", (match_id,))]


def _notify_match_change(db, participant_ids, label, push_title, match_id):
    """Tells a match's players that an admin changed something about it
    (bell + push). The admin who made the change isn't notified about their
    own action. match_id is None when the match no longer exists, so the
    notification isn't wiped by the ON DELETE CASCADE."""
    admin_id = int(current_user.get_id())
    recipients = [uid for uid in participant_ids if uid != admin_id]
    if not recipients:
        return
    db.executemany(
        "INSERT INTO notifications (user_id, kind, label, match_id) VALUES (?, 'reminder', ?, ?)",
        [(uid, label, match_id) for uid in recipients],
    )
    db.commit()
    for uid in recipients:
        send_push_to_user(uid, push_title, label)


def _confirmed_order(db):
    """Confirmed match ids in the same chronological order the Overall replay uses."""
    return [
        r["id"] for r in db.execute(
            "SELECT id FROM matches WHERE status = 'confirmado' ORDER BY match_date ASC, id ASC"
        )
    ]


@bp.route("/jogo/<int:match_id>/data", methods=["POST"])
@login_required
def alterar_data(match_id):
    _require_admin()
    db = get_db()
    match = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if match is None:
        abort(404)

    raw = request.form.get("match_date", "").strip()
    try:
        new_date = datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
    except ValueError:
        flash("Data inválida — escolhe uma data válida.")
        return redirect(url_for("admin.editar_jogo", match_id=match_id))

    old_date = str(match["match_date"])
    if new_date == old_date:
        flash("A data já era essa — nada foi alterado.")
        return redirect(url_for("admin.editar_jogo", match_id=match_id))

    order_before = _confirmed_order(db)
    db.execute("UPDATE matches SET match_date = ? WHERE id = ?", (new_date, match_id))
    # Notifications already sent for this match quote the old date in their
    # text ("...do jogo de 2026-10-01") — keep them in sync.
    # Earlier "admin changed the date" notices are a record of what happened,
    # so they keep their original old -> new wording.
    db.execute(
        "UPDATE notifications SET label = REPLACE(label, ?, ?) WHERE match_id = ? AND label NOT LIKE '% mudou a data do jogo:%'",
        (old_date, new_date, match_id),
    )
    db.commit()
    _notify_match_change(
        db, _match_participant_ids(db, match_id),
        f"{current_user.nickname} (admin) mudou a data do jogo: {old_date} → {new_date}",
        "📅 Data do jogo alterada", match_id,
    )

    message = f"Data do jogo alterada de {old_date} para {new_date}."
    if match["status"] == "confirmado" and _confirmed_order(db) != order_before:
        # The replay orders by (date, id), so moving a confirmed match past
        # another one changes the order Overall *would* be rebuilt in. We do
        # NOT recompute here: that would wipe manual Overall adjustments.
        message += (
            " A ordem dos jogos confirmados mudou — o Overall guardado não foi mexido "
            "(só é recalculado quando corrigires as stats de um jogo confirmado)."
        )
    flash(message)
    return redirect(url_for("admin.editar_jogo", match_id=match_id))


@bp.route("/jogo/<int:match_id>/local", methods=["POST"])
@login_required
def alterar_local(match_id):
    _require_admin()
    db = get_db()
    match = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if match is None:
        abort(404)

    # Empty means "no location" — stored as NULL, same as when a match is
    # created without one. Display-only field: never touches stats/Overall.
    new_location = request.form.get("location", "").strip()[:100] or None
    if new_location == (match["location"] or None):
        flash("O local já era esse — nada foi alterado.")
        return redirect(url_for("admin.editar_jogo", match_id=match_id))

    db.execute("UPDATE matches SET location = ? WHERE id = ?", (new_location, match_id))
    db.commit()
    if new_location:
        label = f"{current_user.nickname} (admin) mudou o local do jogo de {match['match_date']}: {new_location}"
    else:
        label = f"{current_user.nickname} (admin) removeu o local do jogo de {match['match_date']}"
    _notify_match_change(db, _match_participant_ids(db, match_id), label, "📍 Local do jogo alterado", match_id)
    flash(f"Local do jogo alterado para {new_location}." if new_location else "Local do jogo removido.")
    return redirect(url_for("admin.editar_jogo", match_id=match_id))


@bp.route("/jogo/<int:match_id>/apagar", methods=["POST"])
@login_required
def apagar_jogo(match_id):
    _require_admin()
    db = get_db()
    match = db.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if match is None:
        abort(404)

    # Same rule as the creator's delete: confirmed matches have already fed
    # the Overall engine and are never deletable this way.
    if match["status"] != "pendente":
        flash("Só é possível apagar jogos pendentes — este já está confirmado.")
        return redirect(url_for("matches.detalhe", match_id=match_id))

    participant_ids = _match_participant_ids(db, match_id)

    # match_stats, comments and notifications go with it (ON DELETE CASCADE).
    db.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    db.commit()
    _notify_match_change(
        db, participant_ids,
        f"{current_user.nickname} (admin) apagou o jogo pendente de {match['match_date']}",
        "🗑 Jogo apagado", None,
    )
    flash(f"Jogo de {match['match_date']} apagado.")
    return redirect(url_for("admin.painel"))


@bp.route("/exportar.xlsx")
@login_required
def exportar():
    _require_admin()
    db = get_db()
    xlsx_bytes = build_stats_workbook(db)
    filename = f"peladastats-{date.today().isoformat()}.xlsx"
    return Response(
        xlsx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.route("/reset", methods=["POST"])
@login_required
def reset():
    _require_admin()
    if request.form.get("invite_code", "") != current_app.config["INVITE_CODE"]:
        flash("Código de convite incorreto — reset cancelado.")
        return redirect(url_for("admin.painel"))

    db = get_db()
    db.execute("DELETE FROM comments")
    db.execute("DELETE FROM notifications")
    db.execute("DELETE FROM overall_history")
    db.execute("DELETE FROM match_stats")
    db.execute("DELETE FROM matches")
    db.execute("UPDATE users SET overall = ?", (overall_engine.OVERALL_START,))
    db.commit()

    flash("Época resetada — todos os jogadores voltaram ao Overall inicial, sem histórico de jogos.")
    return redirect(url_for("admin.painel"))


@bp.route("/importar", methods=["POST"])
@login_required
def importar():
    _require_admin()
    if request.form.get("invite_code", "") != current_app.config["INVITE_CODE"]:
        flash("Código de convite incorreto — importação cancelada.")
        return redirect(url_for("admin.painel"))

    file = request.files.get("ficheiro")
    if file is None or file.filename == "":
        flash("Escolhe um ficheiro .xlsx para importar.")
        return redirect(url_for("admin.painel"))

    db = get_db()
    try:
        result = import_matches_from_workbook(db, file.stream)
    except ImportError_ as e:
        flash(str(e))
        return redirect(url_for("admin.painel"))

    flash(f"Importação concluída — {result['matches']} jogos repostos, Overall recalculado.")
    return redirect(url_for("admin.painel"))
