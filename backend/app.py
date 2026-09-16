import os

from dotenv import load_dotenv
from flask import Flask
from flask_cors import CORS

from errors import register_error_handlers
from extensions import db
from logging_config import configure_logging
from routes.admin import bp as admin_bp
from routes.auth import bp as auth_bp
from routes.community import bp as community_bp
from routes.security import bp as security_bp
from seed import seed_if_empty

load_dotenv()


def create_app():
    app = Flask(__name__)
    configure_logging(app)
    CORS(app)

    database_url = os.environ.get("DATABASE_URL", "sqlite:///domux.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(security_bp)
    register_error_handlers(app)

    with app.app_context():
        db.create_all()
        seed_if_empty()

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
