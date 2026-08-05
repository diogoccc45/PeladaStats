from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db
from models import User
from overall_engine import OVERALL_START

bp = Blueprint("auth", __name__, url_prefix="/auth")

PES_VALIDOS = ("esquerdo", "direito", "ambidestro")


@bp.route("/registo", methods=["GET", "POST"])
def registo():
    if request.method == "POST":
        form = request.form
        username = form.get("username", "").strip()
        password = form.get("password", "")
        nickname = form.get("nickname", "").strip()
        foot = form.get("foot", "").strip().lower()
        fav_player = form.get("favPlayer", "").strip()
        fav_player_img = form.get("favPlayerImg", "").strip()
        fav_team = form.get("favTeam", "").strip()
        fav_team_logo = form.get("favTeamLogo", "").strip()

        erros = []
        if len(username) < 3:
            erros.append("O username tem de ter pelo menos 3 caracteres.")
        if len(password) < 4:
            erros.append("A password tem de ter pelo menos 4 caracteres.")
        if len(nickname) < 2:
            erros.append("A alcunha tem de ter pelo menos 2 caracteres.")
        if foot not in PES_VALIDOS:
            erros.append("Escolhe o pé preferido.")

        db = get_db()
        if not erros and db.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone():
            erros.append("Esse username já está a ser usado.")

        if erros:
            for erro in erros:
                flash(erro)
            return render_template("auth/registo.html", form=form), 400

        cur = db.execute(
            """
            INSERT INTO users (
                username, password_hash, nickname, preferred_foot,
                favorite_player_name, favorite_player_image_url,
                favorite_team_name, favorite_team_logo_url, overall
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                generate_password_hash(password),
                nickname,
                foot,
                fav_player or None,
                fav_player_img or None,
                fav_team or None,
                fav_team_logo or None,
                OVERALL_START,
            ),
        )
        db.commit()

        user = User.get(cur.lastrowid)
        login_user(user)
        flash(f"Bem-vindo à PeladaStats, {nickname}!")
        return redirect(url_for("dashboard.home"))

    return render_template("auth/registo.html", form={})


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.get_by_username(username)
        if user is None or not check_password_hash(user.password_hash, password):
            flash("Username ou password incorretos.")
            return render_template("auth/login.html", username=username), 401

        login_user(user)
        return redirect(url_for("dashboard.home"))

    return render_template("auth/login.html", username="")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
