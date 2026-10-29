import json

from flask import Flask
from flask_login import LoginManager, current_user

import database
from database import get_db
from models import User


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")

    database.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Entra para veres o dashboard."
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(user_id)

    @app.route("/sw.js")
    def service_worker():
        # Served at the root path (not /static/sw.js) so its default scope
        # covers the whole app — needed for push notifications to work
        # everywhere, not just under /static/. No-cache so the browser
        # always re-checks for a newer version instead of running a stale
        # one indefinitely (this is what caused the stuck-icon issue).
        response = app.send_static_file("sw.js")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    @app.route("/manifest.json")
    def web_app_manifest():
        # Same reasoning as /sw.js — the Add-to-Home-Screen icon shouldn't
        # get stuck on an old cached copy after we update it.
        response = app.send_static_file("manifest.json")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    with app.app_context():
        from app_updates import check_for_new_deploy_safe

        check_for_new_deploy_safe()

    @app.context_processor
    def inject_notifications():
        # Runs on every template render for a logged-in page.
        #
        # Two separate concerns, tracked separately so they don't interfere:
        #   - pending_notifications (celebrated_at): achievement/record
        #     unlocks not yet celebrated — confetti + toast fires for these
        #     once, right here, then they're marked celebrated. This is what
        #     makes the celebration show up reliably for EVERY player who
        #     unlocked something, not just whoever's submission happened to
        #     confirm the match.
        #   - unread_count / recent_notifications (seen_at): everything
        #     (unlocks, reminders, AND deploy updates) shown in the bell
        #     dropdown, marked seen only when the player actually opens it
        #     (via notifications.marcar_vistas) — untouched by page loads,
        #     so the badge persists until they actually check it.
        #
        # vapid_public_key is always exposed (harmless if unused) so any
        # page can offer the "ativar notificações" subscribe button.
        vapid_public_key = app.config["VAPID_PUBLIC_KEY"]
        if not current_user.is_authenticated:
            return {"vapid_public_key": vapid_public_key}
        db = get_db()
        uid = int(current_user.get_id())

        to_celebrate = db.execute(
            "SELECT * FROM notifications WHERE user_id = ? AND kind = 'unlock' AND celebrated_at IS NULL ORDER BY id ASC",
            (uid,),
        ).fetchall()
        if to_celebrate:
            db.execute(
                "UPDATE notifications SET celebrated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND kind = 'unlock' AND celebrated_at IS NULL",
                (uid,),
            )
            db.commit()

        # Post-match recap waiting for this player (see recap.py). Shown as a
        # full-screen overlay, which also covers the unlock toast for the
        # same match — the recap lists those unlocks itself.
        from recap import pending_recap_match_id

        pending_recap_id = pending_recap_match_id(db, uid)

        unread_count = db.execute(
            "SELECT COUNT(*) c FROM notifications WHERE user_id = ? AND seen_at IS NULL", (uid,)
        ).fetchone()["c"]
        recent_notifications = db.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 15", (uid,)
        ).fetchall()
        # "Nova Atualização" pode ter várias linhas (texto do commit) — o
        # sino só mostra a primeira linha, o resto fica neste JSON para o
        # popup ao clicar (ver base_app.html).
        update_texts = {n["id"]: n["label"] for n in recent_notifications if n["kind"] == "update"}

        return {
            "pending_notifications": to_celebrate,
            "pending_recap_id": pending_recap_id,
            "unread_count": unread_count,
            "recent_notifications": recent_notifications,
            "vapid_public_key": vapid_public_key,
            "update_texts_json": json.dumps(update_texts),
        }

    import admin
    import auth
    import comparar
    import dashboard
    import matches
    import notifications
    import profile
    import records
    import settings

    app.register_blueprint(admin.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(matches.bp)
    app.register_blueprint(notifications.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(records.bp)
    app.register_blueprint(comparar.bp)
    app.register_blueprint(settings.bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
