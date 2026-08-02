from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from database import get_db

bp = Blueprint("settings", __name__, url_prefix="/definicoes")

PES_VALIDOS = ("esquerdo", "direito", "ambidestro")


def _parse_float(value, default, lo, hi):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


@bp.route("/", methods=["GET", "POST"])
@login_required
def definicoes():
    db = get_db()
    user_id = int(current_user.get_id())

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
                    favorite_team_name = ?, favorite_team_logo_url = ?, favorite_team_logo_zoom = ?,
                    favorite_team_logo_pos_x = ?, favorite_team_logo_pos_y = ?
                WHERE id = ?
                """,
                (
                    nickname, foot, fav_player or None,
                    fav_player_img or None, player_zoom, player_x, player_y,
                    fav_team or None, fav_team_logo or None, team_zoom, team_x, team_y,
                    user_id,
                ),
            )
            db.commit()
            flash("Perfil atualizado.")
        return redirect(url_for("settings.definicoes"))

    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return render_template("settings.html", user=user)
