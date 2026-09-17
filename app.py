import logging
from pathlib import Path
from typing import Any

from flask import Flask
from flask_cors import CORS

from config import Config
from extensions import init_services
from routes.api_routes import api_bp
from routes.main_routes import main_bp
from services import database

logger = logging.getLogger(__name__)


def configure_logging(app: Flask) -> None:
    """Configure process logging from application settings."""
    log_file = Path(app.config["LOG_FILE"])
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, app.config["LOG_LEVEL"]),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )


def create_app(
    config: dict[str, Any] | None = None,
    services: dict[str, Any] | None = None,
) -> Flask:
    """Create and configure an application with replaceable dependencies."""
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        app.config.update(config)

    if not app.config.get("TESTING"):
        Config.validate()
        configure_logging(app)

    cors_origins = app.config["CORS_ORIGINS"]
    if cors_origins == ["*"]:
        logger.warning(
            "CORS is configured to allow all origins. "
            "This is not recommended for production."
        )
        CORS(app)
    else:
        CORS(app, origins=cors_origins)

    init_services(app, services)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)

    with app.app_context():
        database.init_db()

    logger.info("Application initialized with Blueprints")
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=app.config["DEBUG"], host="0.0.0.0", port=5001)  # noqa: S104
