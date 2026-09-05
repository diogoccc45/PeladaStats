"""
Detects a new code deployment by comparing the current git commit against
the last one we already notified everyone about. When it changed, creates
a "Nova Atualização" notification (+ push) for every player, using the
commit message as the content — the "clique para ver tudo" bit is handled
in base_app.html, this module only decides WHETHER to notify and WHAT to
say.

Runs once per WSGI process start (called from create_app()). Deliberately
defensive: a missing git binary, a repo-less deployment, or the database
not being ready yet (e.g. the very first run, before init-db) should never
be able to break app startup — see the try/except at the call site.
"""
import logging
import subprocess

from config import BASE_DIR
from database import get_db


def _git_output(args):
    return subprocess.check_output(
        ["git"] + args, cwd=BASE_DIR, text=True, stderr=subprocess.DEVNULL
    ).strip()


def check_for_new_deploy():
    commit_hash = _git_output(["rev-parse", "HEAD"])
    commit_message = _git_output(["log", "-1", "--pretty=%B"])

    db = get_db()
    row = db.execute("SELECT value FROM app_meta WHERE key = 'last_notified_commit'").fetchone()
    last_hash = row["value"] if row else None

    if last_hash == commit_hash:
        return  # já processado (ou é a primeira vez a seguir a este commit)

    if last_hash is not None:
        # Não é a primeira vez que isto corre — há mesmo código novo desde a
        # última vez, avisa todos. Na primeiríssima vez (last_hash is None,
        # tabela app_meta acabada de ser criada) só regista o commit atual,
        # sem notificar — para não despejar o histórico de commits antigos
        # de uma vez quando a funcionalidade é ligada.
        from push import send_push_to_user

        user_ids = [r["id"] for r in db.execute("SELECT id FROM users")]
        if user_ids:
            db.executemany(
                "INSERT INTO notifications (user_id, kind, label) VALUES (?, 'update', ?)",
                [(uid, commit_message) for uid in user_ids],
            )
            db.commit()
            subject = commit_message.split("\n", 1)[0].strip()
            for uid in user_ids:
                send_push_to_user(uid, "🆕 Nova Atualização", subject)

    db.execute(
        """
        INSERT INTO app_meta (key, value) VALUES ('last_notified_commit', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (commit_hash,),
    )
    db.commit()


def check_for_new_deploy_safe():
    try:
        check_for_new_deploy()
    except Exception as e:
        logging.info("Verificação de nova versão ignorada: %s", e)
