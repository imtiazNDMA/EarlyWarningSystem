from flask import Flask
from flask_cors import CORS
import logging
import os

# Import configuration and setup
from config import Config
from services import database

# Import Blueprints
from routes.main_routes import main_bp
from routes.api_routes import api_bp

# Configure logging
os.makedirs(
    os.path.dirname(Config.LOG_FILE) if os.path.dirname(Config.LOG_FILE) else ".",
    exist_ok=True,
)
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(Config.LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH

# Enable CORS with proper configuration
if Config.CORS_ORIGINS == ["*"]:
    logger.warning(
        "CORS is configured to allow all origins. This is not recommended for production."
    )
    CORS(app)
else:
    CORS(app, origins=Config.CORS_ORIGINS)

# Initialize Database
database.init_db()

# Register Blueprints
app.register_blueprint(main_bp)
app.register_blueprint(api_bp)

logger.info("Application initialized with Blueprints")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
