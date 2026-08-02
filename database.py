import sqlite3
from datetime import date, timedelta

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash

from overall_engine import apply_overall_updates


def get_db():
    """Devolve a ligação à base de dados para o pedido atual, criando-a se necessário."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))


@click.command("init-db")
def init_db_command():
    """Apaga os dados existentes e recria as tabelas a partir de schema.sql."""
    init_db()
    click.echo("Base de dados inicializada.")


@click.command("seed-demo")
def seed_demo_command():
    """Cria 3 jogadores de demonstração com uma pelada já confirmada, para veres o dashboard populado."""
    db = get_db()

    demo_users = [
        dict(
            username="rafa",
            password="pelada123",
            nickname="Rafa",
            preferred_foot="direito",
            favorite_player_name="Cristiano Ronaldo",
            favorite_player_image_url="",
            favorite_team_name="Al Nassr",
            favorite_team_logo_url="",
        ),
        dict(
            username="diogo",
            password="pelada123",
            nickname="Diogo",
            preferred_foot="esquerdo",
            favorite_player_name="Bernardo Silva",
            favorite_player_image_url="",
            favorite_team_name="Manchester City",
            favorite_team_logo_url="",
        ),
        dict(
            username="tomas",
            password="pelada123",
            nickname="Tomás",
            preferred_foot="direito",
            favorite_player_name="Pedri",
            favorite_player_image_url="",
            favorite_team_name="FC Barcelona",
            favorite_team_logo_url="",
        ),
    ]

    user_ids = {}
    for u in demo_users:
        cur = db.execute(
            """
            INSERT INTO users (
                username, password_hash, nickname, preferred_foot,
                favorite_player_name, favorite_player_image_url,
                favorite_team_name, favorite_team_logo_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                u["username"],
                generate_password_hash(u["password"]),
                u["nickname"],
                u["preferred_foot"],
                u["favorite_player_name"],
                u["favorite_player_image_url"],
                u["favorite_team_name"],
                u["favorite_team_logo_url"],
            ),
        )
        user_ids[u["username"]] = cur.lastrowid

    match_date = (date.today() - timedelta(days=3)).isoformat()
    cur = db.execute(
        """
        INSERT INTO matches (match_date, location, team_a_score, team_b_score, status)
        VALUES (?, ?, ?, ?, 'confirmado')
        """,
        (match_date, "Campo do Bairro", 5, 3),
    )
    match_id = cur.lastrowid

    stats = [
        (match_id, user_ids["rafa"], "A", 3, 1, user_ids["diogo"], 1),
        (match_id, user_ids["diogo"], "A", 2, 0, user_ids["rafa"], 1),
        (match_id, user_ids["tomas"], "B", 3, 1, user_ids["rafa"], 1),
    ]
    db.executemany(
        """
        INSERT INTO match_stats (match_id, user_id, team, goals, assists, mvp_vote_for, submitted)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        stats,
    )
    db.commit()

    # Corre o motor de Overall a sério neste jogo, tal como aconteceria numa
    # confirmação normal — sem isto, o histórico ficava vazio e a seta de
    # tendência no dashboard não tinha nada para mostrar.
    apply_overall_updates(db, match_id)

    click.echo("Dados de demonstração criados (utilizadores: rafa, diogo, tomas — password: pelada123).")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)
