from flask import Flask
from flask_login import LoginManager

import database
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

    import admin
    import auth
    import comparar
    import dashboard
    import matches
    import profile
    import records
    import settings

    app.register_blueprint(admin.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(matches.bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(records.bp)
    app.register_blueprint(comparar.bp)
    app.register_blueprint(settings.bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
