"""
Flask application factory.
"""
import os
from pathlib import Path
from flask import Flask
from .extensions import db, cors, migrate
from .config import config


def create_app(config_name: str = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Load config
    env = config_name or os.getenv('FLASK_ENV', 'development')
    app.config.from_object(config.get(env, config['default']))

    # Ensure data directories exist
    for folder in [
        app.config['UPLOAD_FOLDER'],
        app.config['ANNOTATED_FOLDER'],
        app.config['CARD_DB_FOLDER'],
    ]:
        Path(folder).mkdir(parents=True, exist_ok=True)

    # Init extensions
    db.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config['CORS_ORIGINS']}})
    migrate.init_app(app, db)

    # Register blueprints
    from .api.health import bp as health_bp
    from .api.checkin import bp as checkin_bp
    from .api.cubes import bp as cubes_bp
    from .api.tournaments import bp as tournaments_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(checkin_bp, url_prefix='/api/checkin')
    app.register_blueprint(cubes_bp, url_prefix='/api/cubes')
    app.register_blueprint(tournaments_bp, url_prefix='/api/tournaments')

    # Create tables in dev
    with app.app_context():
        db.create_all()

    return app

