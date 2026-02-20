#!/usr/bin/env bash
# bootstrap.sh — writes all source files into the repo.
# Run once from the project root: bash bootstrap.sh
# Safe to re-run; never touches .env files or data directories.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$SCRIPT_DIR/backend"
FRONTEND="$SCRIPT_DIR/frontend"

write() {
    # write DEST MARKER <<'MARKER' ... MARKER
    # Usage: write_file <dest_path> <src_content_via_heredoc>
    # We use a helper so callers just pass the destination path.
    :
}

echo "▶ Writing backend files..."

mkdir -p "$BACKEND/."
cat > "$BACKEND/wsgi.py" << 'FILEOF'
"""WSGI entry point."""
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

FILEOF

mkdir -p "$BACKEND/app"
cat > "$BACKEND/app/__init__.py" << 'FILEOF'
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

FILEOF

mkdir -p "$BACKEND/app"
cat > "$BACKEND/app/config.py" << 'FILEOF'
"""
Configuration classes for different environments.
"""
import os
from pathlib import Path

# Resolve paths relative to the backend package root
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"


class Config:
    """Base configuration."""

    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'cube_tracker.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    # File storage
    UPLOAD_FOLDER = str(DATA_DIR / "uploads")
    ANNOTATED_FOLDER = str(DATA_DIR / "annotated")
    CARD_DB_FOLDER = str(DATA_DIR / "cards")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    # OCR
    TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")

    # Card detection
    MIN_CARD_AREA = 5000
    MAX_CARD_AREA = 300000
    FUZZY_MATCH_THRESHOLD = 70

    # CORS — comma-separated list of allowed origins
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    SQLALCHEMY_ECHO = False  # set True to see SQL in console


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql://user:pass@localhost/cube_tracker",
    )


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    CARD_DB_FOLDER = str(BASE_DIR / "tests" / "fixtures" / "cards")


config: dict[str, type[Config]] = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}

FILEOF

mkdir -p "$BACKEND/app"
cat > "$BACKEND/app/extensions.py" << 'FILEOF'
"""
Flask extensions — instantiated here, initialized in the app factory.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_migrate import Migrate

db = SQLAlchemy()
cors = CORS()
migrate = Migrate()

FILEOF

mkdir -p "$BACKEND/app/api"
cat > "$BACKEND/app/api/__init__.py" << 'FILEOF'
# API blueprints are registered in app/__init__.py

FILEOF

mkdir -p "$BACKEND/app/api"
cat > "$BACKEND/app/api/health.py" << 'FILEOF'
"""Health check endpoint."""
from flask import Blueprint, jsonify

bp = Blueprint('health', __name__)


@bp.get('/api/health')
def health():
    return jsonify({'status': 'ok'})

FILEOF

mkdir -p "$BACKEND/app/api"
cat > "$BACKEND/app/api/checkin.py" << 'FILEOF'
"""
Check-in API.

Flow:
  POST /api/checkin/start          → create cube + session, return session_id
  POST /api/checkin/<sid>/upload   → upload image, run detection, return cards
  PATCH /api/checkin/<sid>/cards/<card_id> → update a card name
  POST /api/checkin/<sid>/finalize → mark cube CHECKED_IN
  GET  /api/checkin/<sid>          → get current session state
"""
import os
import uuid
import logging
from pathlib import Path
from flask import Blueprint, current_app, jsonify, request

from ..extensions import db
from ..models import Cube, Card, CubeStatus, CardStatus
from ..services.cube_checkin_service import CubeCheckinService

logger = logging.getLogger(__name__)
bp = Blueprint('checkin', __name__)


def _get_service() -> CubeCheckinService:
    cfg = current_app.config
    return CubeCheckinService(
        card_db_folder=cfg['CARD_DB_FOLDER'],
        upload_folder=cfg['UPLOAD_FOLDER'],
        annotated_folder=cfg['ANNOTATED_FOLDER'],
        min_card_area=cfg.get('MIN_CARD_AREA', 5000),
        max_card_area=cfg.get('MAX_CARD_AREA', 300000),
        fuzzy_threshold=cfg.get('FUZZY_MATCH_THRESHOLD', 70),
    )


# ── Start a check-in session ──────────────────────────────────────────────────

@bp.post('/start')
def start_checkin():
    """
    Create a Cube record and return a session_id.

    Body (JSON):
      tournament_id: int
      owner_name: str
      owner_email: str (optional)
      cube_name: str
    """
    data = request.get_json(silent=True) or {}

    tournament_id = data.get('tournament_id')
    owner_name = data.get('owner_name', '').strip()
    cube_name = data.get('cube_name', '').strip()

    if not tournament_id or not owner_name or not cube_name:
        return jsonify({'error': 'tournament_id, owner_name, and cube_name are required'}), 400

    session_id = str(uuid.uuid4())

    cube = Cube(
        tournament_id=tournament_id,
        owner_name=owner_name,
        owner_email=data.get('owner_email', ''),
        cube_name=cube_name,
        session_id=session_id,
        status=CubeStatus.PENDING_CHECKIN,
    )
    db.session.add(cube)
    db.session.commit()

    return jsonify({'session_id': session_id, 'cube': cube.to_dict()}), 201


# ── Get session state ─────────────────────────────────────────────────────────

@bp.get('/<session_id>')
def get_session(session_id):
    cube = Cube.query.filter_by(session_id=session_id).first_or_404()
    data = cube.to_dict(include_relations=True)

    # Attach annotated image URL if available
    if cube.annotated_image_path and os.path.exists(cube.annotated_image_path):
        data['annotated_image_url'] = f'/api/checkin/{session_id}/annotated'

    return jsonify(data)


# ── Upload + process image ────────────────────────────────────────────────────

@bp.post('/<session_id>/upload')
def upload_image(session_id):
    """
    Accept a multipart image upload, run detection pipeline, persist cards.
    Returns the detected card list.
    """
    cube = Cube.query.filter_by(session_id=session_id).first_or_404()

    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    # Save original
    ext = Path(file.filename).suffix or '.jpg'
    filename = f"{session_id}{ext}"
    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    file.save(upload_path)

    cube.source_image_path = upload_path
    db.session.flush()

    try:
        service = _get_service()
        cards = service.process_image(upload_path, cube)

        # Persist cards
        for card in cards:
            db.session.add(card)
        db.session.flush()

        # Render annotated image
        annotated_filename = f"{session_id}_annotated.jpg"
        annotated_path = os.path.join(
            current_app.config['ANNOTATED_FOLDER'], annotated_filename
        )
        service.render_annotated_image(upload_path, cards, annotated_path)
        cube.annotated_image_path = annotated_path
        cube.total_cards = len(cards)

        db.session.commit()

    except Exception as exc:
        db.session.rollback()
        logger.exception("Image processing failed")
        return jsonify({'error': str(exc)}), 500

    return jsonify({
        'cards': [c.to_dict() for c in cards],
        'total_detected': len(cards),
        'annotated_image_url': f'/api/checkin/{session_id}/annotated',
    }), 200


# ── Serve annotated image ─────────────────────────────────────────────────────

@bp.get('/<session_id>/annotated')
def get_annotated(session_id):
    from flask import send_file
    cube = Cube.query.filter_by(session_id=session_id).first_or_404()
    if not cube.annotated_image_path or not os.path.exists(cube.annotated_image_path):
        return jsonify({'error': 'Annotated image not available'}), 404
    return send_file(cube.annotated_image_path, mimetype='image/jpeg')


# ── Update a single card ──────────────────────────────────────────────────────

@bp.patch('/<session_id>/cards/<int:card_id>')
def update_card(session_id, card_id):
    """
    Confirm / correct a card name.

    Body (JSON):
      confirmed_name: str
    """
    cube = Cube.query.filter_by(session_id=session_id).first_or_404()
    card = Card.query.filter_by(id=card_id, cube_id=cube.id).first_or_404()

    data = request.get_json(silent=True) or {}
    confirmed_name = data.get('confirmed_name', '').strip()

    if not confirmed_name:
        return jsonify({'error': 'confirmed_name is required'}), 400

    service = _get_service()
    service.update_card_name(card, confirmed_name)

    return jsonify(card.to_dict())


# ── Finalize check-in ─────────────────────────────────────────────────────────

@bp.post('/<session_id>/finalize')
def finalize(session_id):
    cube = Cube.query.filter_by(session_id=session_id).first_or_404()

    service = _get_service()
    service.finalize_cube(cube)

    return jsonify(cube.to_dict(include_relations=True))


# ── List cards for a session ──────────────────────────────────────────────────

@bp.get('/<session_id>/cards')
def list_cards(session_id):
    cube = Cube.query.filter_by(session_id=session_id).first_or_404()
    cards = Card.query.filter_by(cube_id=cube.id).order_by(Card.bbox_y, Card.bbox_x).all()
    return jsonify([c.to_dict() for c in cards])

FILEOF

mkdir -p "$BACKEND/app/api"
cat > "$BACKEND/app/api/cubes.py" << 'FILEOF'
"""Cubes REST API."""
from flask import Blueprint, jsonify, request
from ..extensions import db
from ..models import Cube, Card, CubeStatus

bp = Blueprint('cubes', __name__)


@bp.get('/')
def list_cubes():
    tournament_id = request.args.get('tournament_id', type=int)
    q = Cube.query
    if tournament_id:
        q = q.filter_by(tournament_id=tournament_id)
    cubes = q.order_by(Cube.created_at.desc()).all()
    return jsonify([c.to_dict() for c in cubes])


@bp.get('/<int:cube_id>')
def get_cube(cube_id):
    cube = Cube.query.get_or_404(cube_id)
    return jsonify(cube.to_dict(include_relations=True))


@bp.get('/<int:cube_id>/cards')
def get_cube_cards(cube_id):
    cube = Cube.query.get_or_404(cube_id)
    cards = Card.query.filter_by(cube_id=cube.id).order_by(Card.bbox_y, Card.bbox_x).all()
    return jsonify([c.to_dict() for c in cards])


@bp.delete('/<int:cube_id>')
def delete_cube(cube_id):
    cube = Cube.query.get_or_404(cube_id)
    db.session.delete(cube)
    db.session.commit()
    return '', 204

FILEOF

mkdir -p "$BACKEND/app/api"
cat > "$BACKEND/app/api/tournaments.py" << 'FILEOF'
"""Tournaments REST API."""
from datetime import date
from flask import Blueprint, jsonify, request
from ..extensions import db
from ..models import Tournament, TournamentStatus

bp = Blueprint('tournaments', __name__)


@bp.get('/')
def list_tournaments():
    tournaments = Tournament.query.order_by(Tournament.date.desc()).all()
    return jsonify([t.to_dict() for t in tournaments])


@bp.post('/')
def create_tournament():
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    date_str = data.get('date')

    if not name or not date_str:
        return jsonify({'error': 'name and date are required'}), 400

    try:
        tournament_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': 'date must be ISO format (YYYY-MM-DD)'}), 400

    tournament = Tournament(
        name=name,
        date=tournament_date,
        location=data.get('location', ''),
        notes=data.get('notes', ''),
        status=TournamentStatus.DRAFT,
    )
    db.session.add(tournament)
    db.session.commit()
    return jsonify(tournament.to_dict()), 201


@bp.get('/<int:tournament_id>')
def get_tournament(tournament_id):
    t = Tournament.query.get_or_404(tournament_id)
    return jsonify(t.to_dict(include_relations=True))


@bp.patch('/<int:tournament_id>')
def update_tournament(tournament_id):
    t = Tournament.query.get_or_404(tournament_id)
    data = request.get_json(silent=True) or {}

    if 'name' in data:
        t.name = data['name']
    if 'location' in data:
        t.location = data['location']
    if 'notes' in data:
        t.notes = data['notes']
    if 'status' in data:
        t.status = TournamentStatus(data['status'])

    db.session.commit()
    return jsonify(t.to_dict())


@bp.delete('/<int:tournament_id>')
def delete_tournament(tournament_id):
    t = Tournament.query.get_or_404(tournament_id)
    db.session.delete(t)
    db.session.commit()
    return '', 204

FILEOF

mkdir -p "$BACKEND/app/models"
cat > "$BACKEND/app/models/__init__.py" << 'FILEOF'
"""
Core domain models for the cube card tracking system.
"""
from enum import Enum
from datetime import datetime
from ..extensions import db


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseModel(db.Model):
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


# ── Enums ─────────────────────────────────────────────────────────────────────

class TournamentStatus(str, Enum):
    DRAFT = 'draft'
    ACTIVE = 'active'
    COMPLETE = 'complete'
    CANCELLED = 'cancelled'


class CubeStatus(str, Enum):
    PENDING_CHECKIN = 'pending_checkin'
    CHECKED_IN = 'checked_in'
    IN_USE = 'in_use'
    RETURNED = 'returned'
    FLAGGED = 'flagged'


class TableStatus(str, Enum):
    WAITING = 'waiting'
    DRAFTING = 'drafting'
    PLAYING = 'playing'
    COMPLETE = 'complete'


class CardStatus(str, Enum):
    DETECTED = 'detected'
    CONFIRMED = 'confirmed'
    DRAFTED = 'drafted'
    RETURNED = 'returned'


# ── Models ────────────────────────────────────────────────────────────────────

class Tournament(BaseModel):
    __tablename__ = 'tournaments'

    name = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(200))
    status = db.Column(db.Enum(TournamentStatus), nullable=False, default=TournamentStatus.DRAFT)
    notes = db.Column(db.Text)

    cubes = db.relationship('Cube', back_populates='tournament', cascade='all, delete-orphan')
    tables = db.relationship('Table', back_populates='tournament', cascade='all, delete-orphan')

    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data.update({
            'name': self.name,
            'date': self.date.isoformat() if self.date else None,
            'location': self.location,
            'status': self.status.value,
            'notes': self.notes,
        })
        if include_relations:
            data['cubes'] = [c.to_dict() for c in self.cubes]
            data['tables'] = [t.to_dict() for t in self.tables]
        return data


class Cube(BaseModel):
    __tablename__ = 'cubes'

    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    owner_name = db.Column(db.String(200), nullable=False)
    owner_email = db.Column(db.String(200))
    cube_name = db.Column(db.String(200), nullable=False)
    status = db.Column(db.Enum(CubeStatus), nullable=False, default=CubeStatus.PENDING_CHECKIN)

    source_image_path = db.Column(db.String(500))
    annotated_image_path = db.Column(db.String(500))
    session_id = db.Column(db.String(100), unique=True)

    total_cards = db.Column(db.Integer, default=0)
    cards_confirmed = db.Column(db.Integer, default=0)

    tournament = db.relationship('Tournament', back_populates='cubes')
    cards = db.relationship('Card', back_populates='cube', cascade='all, delete-orphan')
    tables = db.relationship('Table', back_populates='cube')

    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data.update({
            'tournament_id': self.tournament_id,
            'owner_name': self.owner_name,
            'owner_email': self.owner_email,
            'cube_name': self.cube_name,
            'status': self.status.value,
            'session_id': self.session_id,
            'total_cards': self.total_cards,
            'cards_confirmed': self.cards_confirmed,
            'annotated_image_path': self.annotated_image_path,
        })
        if include_relations:
            data['cards'] = [c.to_dict() for c in self.cards]
        return data


class Card(BaseModel):
    __tablename__ = 'cards'

    cube_id = db.Column(db.Integer, db.ForeignKey('cubes.id'), nullable=False)

    raw_ocr_text = db.Column(db.String(200))
    recognized_name = db.Column(db.String(200))
    confirmed_name = db.Column(db.String(200))
    match_score = db.Column(db.Float)
    status = db.Column(db.Enum(CardStatus), nullable=False, default=CardStatus.DETECTED)

    bbox_x = db.Column(db.Integer)
    bbox_y = db.Column(db.Integer)
    bbox_width = db.Column(db.Integer)
    bbox_height = db.Column(db.Integer)
    polygon_json = db.Column(db.JSON)

    thumbnail_base64 = db.Column(db.Text)

    cube = db.relationship('Cube', back_populates='cards')
    assignments = db.relationship('CardAssignment', back_populates='card', cascade='all, delete-orphan')

    @property
    def display_name(self):
        return self.confirmed_name or self.recognized_name or self.raw_ocr_text or 'Unknown Card'

    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data.update({
            'cube_id': self.cube_id,
            'raw_ocr_text': self.raw_ocr_text,
            'recognized_name': self.recognized_name,
            'confirmed_name': self.confirmed_name,
            'match_score': self.match_score,
            'status': self.status.value,
            'display_name': self.display_name,
            'bbox_x': self.bbox_x,
            'bbox_y': self.bbox_y,
            'bbox_width': self.bbox_width,
            'bbox_height': self.bbox_height,
            'polygon_json': self.polygon_json,
            'thumbnail_base64': self.thumbnail_base64,
        })
        if include_relations:
            data['assignments'] = [a.to_dict() for a in self.assignments]
        return data


class Table(BaseModel):
    __tablename__ = 'tables'

    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    cube_id = db.Column(db.Integer, db.ForeignKey('cubes.id'))
    table_number = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Enum(TableStatus), nullable=False, default=TableStatus.WAITING)

    tournament = db.relationship('Tournament', back_populates='tables')
    cube = db.relationship('Cube', back_populates='tables')
    players = db.relationship('Player', back_populates='table', cascade='all, delete-orphan')

    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data.update({
            'tournament_id': self.tournament_id,
            'cube_id': self.cube_id,
            'table_number': self.table_number,
            'status': self.status.value,
        })
        if include_relations:
            data['players'] = [p.to_dict() for p in self.players]
        return data


class Player(BaseModel):
    __tablename__ = 'players'

    table_id = db.Column(db.Integer, db.ForeignKey('tables.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    seat_number = db.Column(db.Integer, nullable=False)

    draft_submitted = db.Column(db.Boolean, default=False)
    cards_returned = db.Column(db.Boolean, default=False)

    table = db.relationship('Table', back_populates='players')
    assignments = db.relationship('CardAssignment', back_populates='player', cascade='all, delete-orphan')

    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data.update({
            'table_id': self.table_id,
            'name': self.name,
            'seat_number': self.seat_number,
            'draft_submitted': self.draft_submitted,
            'cards_returned': self.cards_returned,
        })
        return data


class CardAssignment(BaseModel):
    __tablename__ = 'card_assignments'

    card_id = db.Column(db.Integer, db.ForeignKey('cards.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('players.id'), nullable=False)

    assigned_at = db.Column(db.DateTime)
    returned_at = db.Column(db.DateTime)

    card = db.relationship('Card', back_populates='assignments')
    player = db.relationship('Player', back_populates='assignments')

    def to_dict(self, include_relations=False):
        data = super().to_dict()
        data.update({
            'card_id': self.card_id,
            'player_id': self.player_id,
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'returned_at': self.returned_at.isoformat() if self.returned_at else None,
        })
        if include_relations:
            data['card'] = self.card.to_dict()
            data['player'] = self.player.to_dict()
        return data

FILEOF

mkdir -p "$BACKEND/app/models"
cat > "$BACKEND/app/models/base.py" << 'FILEOF'
"""
Base SQLAlchemy model with common fields.
"""
from datetime import datetime
from .extensions import db


class BaseModel(db.Model):
    """Abstract base with id, created_at, updated_at."""
    
    __abstract__ = True
    
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

FILEOF

mkdir -p "$BACKEND/app/services"
cat > "$BACKEND/app/services/__init__.py" << 'FILEOF'
# Services package

FILEOF

mkdir -p "$BACKEND/app/services"
cat > "$BACKEND/app/services/card_db_service.py" << 'FILEOF'
"""
Card database service.
Loads card names from JSON/text files and provides fuzzy matching.
"""
import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import process, fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False
    logger.warning("rapidfuzz not available — fuzzy matching disabled")


class CardDatabaseService:
    """Manages the list of known card names and fuzzy-matches OCR output."""

    def __init__(self, card_db_folder: str):
        self.card_db_folder = Path(card_db_folder)
        self._card_names: List[str] = []
        self._loaded = False

    def ensure_loaded(self):
        """Load card names if not already loaded."""
        if not self._loaded:
            self._load()
            self._loaded = True

    def _load(self):
        """
        Load card names from the card DB folder.

        Supports:
          - oracle-cards.json  (Scryfall bulk data — list of objects with "name")
          - cards.json         (simple list of strings or objects)
          - cards.txt          (one name per line)
        """
        names = set()

        for path in self.card_db_folder.glob('*.json'):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, str):
                            names.add(item.strip())
                        elif isinstance(item, dict) and 'name' in item:
                            # Handle split/transform cards — keep front face only
                            name = item['name'].split(' // ')[0].strip()
                            names.add(name)
                elif isinstance(data, dict) and 'data' in data:
                    for item in data['data']:
                        if isinstance(item, dict) and 'name' in item:
                            names.add(item['name'].split(' // ')[0].strip())
                logger.info(f"Loaded names from {path.name}")
            except Exception as exc:
                logger.warning(f"Failed to load {path}: {exc}")

        for path in self.card_db_folder.glob('*.txt'):
            try:
                for line in path.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if line and not line.startswith('#'):
                        names.add(line)
            except Exception as exc:
                logger.warning(f"Failed to load {path}: {exc}")

        self._card_names = sorted(names)
        logger.info(f"Card database loaded: {len(self._card_names)} unique names")

    @property
    def card_names(self) -> List[str]:
        self.ensure_loaded()
        return self._card_names

    def fuzzy_match(
        self,
        query: str,
        threshold: int = 70
    ) -> Optional[Tuple[str, float]]:
        """
        Find the best matching card name for an OCR string.

        Returns (name, score) or None if no match above threshold.
        """
        if not query or not self._card_names:
            return None

        if not RAPIDFUZZ_AVAILABLE:
            return None

        result = process.extractOne(
            query,
            self._card_names,
            scorer=fuzz.WRatio,
            score_cutoff=threshold,
        )
        if result is None:
            return None

        name, score, _ = result
        return name, round(score / 100, 3)

    def search(self, query: str, limit: int = 10) -> List[str]:
        """Return top matching card names for autocomplete."""
        if not query or not RAPIDFUZZ_AVAILABLE:
            return []
        results = process.extract(
            query, self._card_names, scorer=fuzz.WRatio, limit=limit
        )
        return [r[0] for r in results]

FILEOF

mkdir -p "$BACKEND/app/services"
cat > "$BACKEND/app/services/cube_checkin_service.py" << 'FILEOF'
"""
Cube check-in service.
Orchestrates detection, OCR, fuzzy matching, and database persistence.
"""
import base64
import cv2
import numpy as np
import logging
from pathlib import Path
from typing import List, Optional

from ..extensions import db
from ..models import Cube, Card, CardStatus, CubeStatus
from .detection_service import DetectionService
from .ocr_service import OCRService
from .card_db_service import CardDatabaseService

logger = logging.getLogger(__name__)


class CubeCheckinService:
    """High-level service for cube check-in workflow."""

    def __init__(
        self,
        card_db_folder: str,
        upload_folder: str,
        annotated_folder: str,
        min_card_area: int = 5000,
        max_card_area: int = 300000,
        fuzzy_threshold: int = 70,
    ):
        self.detection_service = DetectionService(min_card_area, max_card_area)
        self.ocr_service = OCRService()
        self.card_db_service = CardDatabaseService(card_db_folder)
        self.upload_folder = Path(upload_folder)
        self.annotated_folder = Path(annotated_folder)
        self.fuzzy_threshold = fuzzy_threshold

        self.card_db_service.ensure_loaded()

    def process_image(self, image_path: str, cube: Cube) -> List[Card]:
        """
        Process an uploaded cube image.

        Returns a list of detected Card instances (not yet committed).
        """
        logger.info(f"Processing image for cube {cube.id}: {image_path}")

        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not load image: {image_path}")

        rects = self.detection_service.detect_cards(img)
        logger.info(f"Detected {len(rects)} card regions")

        cards = []
        for rect in rects:
            card = self._process_card_region(img, rect, cube.id)
            if card:
                cards.append(card)

        # Sort left-to-right, top-to-bottom (row height ≈ 80 px)
        cards.sort(key=lambda c: (c.bbox_y // 80, c.bbox_x))

        matched = sum(1 for c in cards if c.recognized_name)
        logger.info(f"Processed {len(cards)} cards, {matched} matched")
        return cards

    def _process_card_region(
        self,
        img: np.ndarray,
        rect,
        cube_id: int,
    ) -> Optional[Card]:
        """Process a single detected card region."""
        (cx, cy), (rw, rh), angle = rect

        if rw <= 0 or rh <= 0:
            return None

        # Ensure portrait orientation
        if rw > rh:
            rw, rh = rh, rw
            angle = (angle + 90) % 180

        box = cv2.boxPoints(((cx, cy), (rw, rh), angle))
        box = np.int32(box)

        x, y, w, h = cv2.boundingRect(box)
        h_img, w_img = img.shape[:2]
        x = max(0, x)
        y = max(0, y)
        x2 = min(w_img, x + w)
        y2 = min(h_img, y + h)
        w = x2 - x
        h = y2 - y

        if w < 30 or h < 30:
            return None

        crop = img[y:y2, x:x2]

        # OCR the top 30 % where the card name lives
        name_height = min(int(h * 0.3), 120)
        name_region = crop[:name_height, :]
        raw_text = self.ocr_service.read_text(name_region)

        match_result = None
        if raw_text:
            match_result = self.card_db_service.fuzzy_match(raw_text, self.fuzzy_threshold)

        recognized_name = match_result[0] if match_result else None
        match_score = match_result[1] if match_result else 0.0

        thumbnail_b64 = self._create_thumbnail(crop)

        card = Card(
            cube_id=cube_id,
            raw_ocr_text=raw_text,
            recognized_name=recognized_name,
            match_score=match_score,
            status=CardStatus.DETECTED,
            bbox_x=x,
            bbox_y=y,
            bbox_width=w,
            bbox_height=h,
            polygon_json=box.tolist(),
            thumbnail_base64=thumbnail_b64,
        )
        return card

    def _create_thumbnail(self, img: np.ndarray, max_size: int = 120) -> str:
        """Create base64-encoded JPEG thumbnail."""
        try:
            h, w = img.shape[:2]
            if h == 0 or w == 0:
                return ''
            scale = min(max_size / w, max_size / h, 1.0)
            new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
            resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            _, buf = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 75])
            return base64.b64encode(buf.tobytes()).decode('utf-8')
        except Exception:
            return ''

    def render_annotated_image(
        self,
        image_path: str,
        cards: List[Card],
        output_path: str,
    ) -> bool:
        """Draw bounding boxes and labels on the source image."""
        try:
            img = cv2.imread(image_path)
            if img is None:
                return False

            for card in cards:
                if not card.polygon_json:
                    continue

                pts = np.array(card.polygon_json, dtype=np.int32)

                if card.confirmed_name:
                    color = (34, 197, 94)    # green
                elif card.recognized_name:
                    color = (251, 191, 36)   # amber
                else:
                    color = (239, 68, 68)    # red

                cv2.polylines(img, [pts], True, color, 3)

                name = card.display_name
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale, thickness = 0.6, 2
                (tw, th), baseline = cv2.getTextSize(name, font, font_scale, thickness)

                lx = card.bbox_x
                ly = max(0, card.bbox_y - 6)

                cv2.rectangle(
                    img,
                    (lx, ly - th - baseline - 4),
                    (lx + tw + 8, ly + 2),
                    color, -1,
                )
                text_color = (30, 30, 30) if color == (251, 191, 36) else (255, 255, 255)
                cv2.putText(
                    img, name,
                    (lx + 4, ly - baseline),
                    font, font_scale, text_color, thickness, cv2.LINE_AA,
                )

            cv2.imwrite(output_path, img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            return True

        except Exception as exc:
            logger.error(f"Failed to render annotated image: {exc}")
            return False

    def update_card_name(self, card: Card, confirmed_name: str):
        card.confirmed_name = confirmed_name
        card.status = CardStatus.CONFIRMED
        db.session.commit()

    def finalize_cube(self, cube: Cube):
        cube.status = CubeStatus.CHECKED_IN
        cube.total_cards = len(cube.cards)
        cube.cards_confirmed = sum(1 for c in cube.cards if c.confirmed_name)
        db.session.commit()

FILEOF

mkdir -p "$BACKEND/app/services"
cat > "$BACKEND/app/services/detection_service.py" << 'FILEOF'
"""
Card detection service.
Finds card-shaped rectangles in an image using OpenCV.
"""
import cv2
import numpy as np
import logging
from typing import List

logger = logging.getLogger(__name__)


class DetectionService:
    """Detects playing card regions in an image."""

    def __init__(self, min_card_area: int = 5000, max_card_area: int = 300000):
        self.min_card_area = min_card_area
        self.max_card_area = max_card_area

    def detect_cards(self, img: np.ndarray) -> List:
        """
        Detect card-shaped contours in the image.

        Returns a list of cv2.minAreaRect tuples:
          ((cx, cy), (w, h), angle)
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Mild blur to reduce noise
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        # Adaptive threshold works well on varied lighting
        thresh = cv2.adaptiveThreshold(
            blur, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            11, 4
        )

        # Morphological closing to connect card edges
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        rects = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if not (self.min_card_area <= area <= self.max_card_area):
                continue

            rect = cv2.minAreaRect(cnt)
            (cx, cy), (rw, rh), angle = rect

            # Skip non-rectangular shapes (cards have ~1.4 aspect ratio)
            if rw == 0 or rh == 0:
                continue
            ratio = max(rw, rh) / min(rw, rh)
            if not (1.1 <= ratio <= 2.5):
                continue

            rects.append(rect)

        logger.debug(f"Detected {len(rects)} card candidates from {len(contours)} contours")
        return rects

FILEOF

mkdir -p "$BACKEND/app/services"
cat > "$BACKEND/app/services/ocr_service.py" << 'FILEOF'
"""
OCR service — wraps pytesseract for card name extraction.
"""
import re
import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract/PIL not available — OCR disabled")


class OCRService:
    """Extract text from card name regions."""

    # Tesseract config: single-line, whitelist printable ASCII
    _CONFIG = '--oem 3 --psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz\' -'

    def read_text(self, img: np.ndarray) -> str:
        """
        Run OCR on a BGR numpy image crop.
        Returns cleaned text, or empty string on failure.
        """
        if not TESSERACT_AVAILABLE:
            return ''
        if img is None or img.size == 0:
            return ''

        try:
            import cv2
            # Upscale small crops for better accuracy
            h, w = img.shape[:2]
            if h < 30 or w < 60:
                return ''

            scale = max(1.0, 60 / h)
            if scale > 1.0:
                img = cv2.resize(img, (int(w * scale), int(h * scale)),
                                 interpolation=cv2.INTER_CUBIC)

            # Greyscale → threshold for cleaner OCR
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            pil_img = Image.fromarray(binary)
            raw = pytesseract.image_to_string(pil_img, config=self._CONFIG)
            return self._clean(raw)

        except Exception as exc:
            logger.debug(f"OCR error: {exc}")
            return ''

    @staticmethod
    def _clean(text: str) -> str:
        """Strip noise from OCR output."""
        text = text.strip()
        # Remove non-printable, keep letters/spaces/apostrophes/hyphens/commas
        text = re.sub(r"[^A-Za-z ',\-]", '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

FILEOF

echo "▶ Writing frontend files..."

mkdir -p "$FRONTEND/."
cat > "$FRONTEND/tsconfig.json" << 'FILEOF'
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "noEmit": true,
    "resolveJsonModule": true,
    "allowImportingTsExtensions": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false
  },
  "include": ["src"]
}

FILEOF

mkdir -p "$FRONTEND/."
cat > "$FRONTEND/package.json" << 'FILEOF'
{
  "name": "cube-card-tracker-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "parcel src/index.html --port 5173",
    "build": "parcel build src/index.html --dist-dir dist",
    "clean": "rm -rf dist .parcel-cache"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@parcel/transformer-typescript-tsc": "^2.12.0",
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "parcel": "^2.12.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.3.2"
  }
}

FILEOF

mkdir -p "$FRONTEND/."
cat > "$FRONTEND/postcss.config.js" << 'FILEOF'
module.exports = {
  plugins: {
    tailwindcss: {},
  },
};

FILEOF

mkdir -p "$FRONTEND/."
cat > "$FRONTEND/tailwind.config.js" << 'FILEOF'
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{html,ts,tsx}'],
  theme: { extend: {} },
  plugins: [],
};

FILEOF

mkdir -p "$FRONTEND/src"
cat > "$FRONTEND/src/index.html" << 'FILEOF'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Cube Card Tracker</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="./main.tsx"></script>
  </body>
</html>

FILEOF

mkdir -p "$FRONTEND/src"
cat > "$FRONTEND/src/index.css" << 'FILEOF'
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  font-family: system-ui, -apple-system, sans-serif;
}

FILEOF

mkdir -p "$FRONTEND/src"
cat > "$FRONTEND/src/main.tsx" << 'FILEOF'
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

FILEOF

mkdir -p "$FRONTEND/src"
cat > "$FRONTEND/src/App.tsx" << 'FILEOF'
import { CheckinPage } from './pages/CheckinPage';

export default function App() {
  return <CheckinPage />;
}


FILEOF

mkdir -p "$FRONTEND/src/api"
cat > "$FRONTEND/src/api/client.ts" << 'FILEOF'
// Backend API base URL.
// Set API_URL in frontend/.env to point at a different host/port.
// Defaults to the same host the page is served from (works when backend proxies the frontend,
// or when the dev script handles the proxy).
const API_URL = process.env.API_URL ?? 'http://localhost:5000';

/**
 * JSON fetch wrapper. Throws a plain Error with the server's message on non-2xx responses.
 */
export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });

  if (res.status === 204) {
    return undefined as T;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? `HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * Multipart file upload. Don't set Content-Type manually — the browser adds
 * the boundary string automatically when you pass a FormData body.
 */
export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? `HTTP ${res.status}`);
  }

  return res.json();
}

// Export so checkin.ts can build image src URLs directly
export { API_URL };

FILEOF

mkdir -p "$FRONTEND/src/api"
cat > "$FRONTEND/src/api/checkin.ts" << 'FILEOF'
import { apiFetch, apiUpload, API_URL } from './client';
import { Card, Cube } from '../types';

export interface StartCheckinPayload {
  tournament_id: number;
  owner_name: string;
  owner_email?: string;
  cube_name: string;
}

export interface StartCheckinResponse {
  session_id: string;
  cube: Cube;
}

export interface UploadResponse {
  cards: Card[];
  total_detected: number;
  annotated_image_url: string;
}

export function startCheckin(payload: StartCheckinPayload): Promise<StartCheckinResponse> {
  return apiFetch('/api/checkin/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getSession(sessionId: string): Promise<Cube> {
  return apiFetch(`/api/checkin/${sessionId}`);
}

export function uploadImage(sessionId: string, file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('image', file);
  return apiUpload(`/api/checkin/${sessionId}/upload`, formData);
}

export function listCards(sessionId: string): Promise<Card[]> {
  return apiFetch(`/api/checkin/${sessionId}/cards`);
}

export function updateCard(sessionId: string, cardId: number, confirmedName: string): Promise<Card> {
  return apiFetch(`/api/checkin/${sessionId}/cards/${cardId}`, {
    method: 'PATCH',
    body: JSON.stringify({ confirmed_name: confirmedName }),
  });
}

export function finalizeCheckin(sessionId: string): Promise<Cube> {
  return apiFetch(`/api/checkin/${sessionId}/finalize`, { method: 'POST' });
}

// Returns a URL the browser can use directly in an <img> src
export function getAnnotatedImageUrl(sessionId: string): string {
  return `${API_URL}/api/checkin/${sessionId}/annotated`;
}

FILEOF

mkdir -p "$FRONTEND/src/api"
cat > "$FRONTEND/src/api/cubes.ts" << 'FILEOF'
import { apiFetch } from './client';
import { Cube, Card } from '../types';

export function listCubes(tournamentId?: number): Promise<Cube[]> {
  const qs = tournamentId ? `?tournament_id=${tournamentId}` : '';
  return apiFetch(`/api/cubes/${qs}`);
}

export function getCube(cubeId: number): Promise<Cube> {
  return apiFetch(`/api/cubes/${cubeId}`);
}

export function getCubeCards(cubeId: number): Promise<Card[]> {
  return apiFetch(`/api/cubes/${cubeId}/cards`);
}

FILEOF

mkdir -p "$FRONTEND/src/api"
cat > "$FRONTEND/src/api/tournaments.ts" << 'FILEOF'
import { apiFetch } from './client';
import { Tournament } from '../types';

export function listTournaments(): Promise<Tournament[]> {
  return apiFetch('/api/tournaments/');
}

export function createTournament(name: string, date: string, location?: string): Promise<Tournament> {
  return apiFetch('/api/tournaments/', {
    method: 'POST',
    body: JSON.stringify({ name, date, location }),
  });
}

export function getTournament(id: number): Promise<Tournament> {
  return apiFetch(`/api/tournaments/${id}`);
}

FILEOF

mkdir -p "$FRONTEND/src/components/checkin"
cat > "$FRONTEND/src/components/checkin/CardCanvas.tsx" << 'FILEOF'
interface Props {
  imageUrl: string;
}

/**
 * Displays the annotated image that the backend draws bounding boxes onto.
 * All annotation is done server-side, so this is just a styled <img>.
 */
export function CardCanvas({ imageUrl }: Props) {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 overflow-auto max-h-[60vh]">
      <img
        src={imageUrl}
        alt="Annotated card scan"
        className="w-full h-auto object-contain"
      />
    </div>
  );
}

FILEOF

mkdir -p "$FRONTEND/src/components/checkin"
cat > "$FRONTEND/src/components/checkin/CardList.tsx" << 'FILEOF'
import { useState } from 'react';
import { updateCard } from '../../api/checkin';
import { Card } from '../../types';

interface Props {
  cards: Card[];
  sessionId: string;
  onCardUpdated: (card: Card) => void;
}

export function CardList({ cards, sessionId, onCardUpdated }: Props) {
  // Which card is currently being edited, and the draft value
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState('');
  const [savingId, setSavingId] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  function startEdit(card: Card) {
    setEditingId(card.id);
    setEditValue(card.confirmed_name ?? card.recognized_name ?? '');
    setSaveError(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setSaveError(null);
  }

  async function saveEdit(card: Card) {
    const name = editValue.trim();
    if (!name) return;

    setSavingId(card.id);
    setSaveError(null);
    try {
      const updated = await updateCard(sessionId, card.id, name);
      onCardUpdated(updated);
      setEditingId(null);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSavingId(null);
    }
  }

  if (cards.length === 0) {
    return (
      <p className="text-center py-10 text-gray-400">
        No cards detected yet. Upload an image to begin.
      </p>
    );
  }

  const identified = cards.filter((c) => c.confirmed_name ?? c.recognized_name).length;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <span className="font-medium text-gray-700">
          {cards.length} card{cards.length !== 1 ? 's' : ''} detected
        </span>
        <span className="text-sm text-gray-500">{identified} identified</span>
      </div>

      {saveError && (
        <p className="mb-2 text-sm text-red-600">{saveError}</p>
      )}

      <ul className="space-y-2">
        {cards.map((card) => {
          const isEditing = editingId === card.id;
          const isSaving = savingId === card.id;

          // Pick row colour based on match status
          const rowClass = card.confirmed_name
            ? 'bg-green-50 border-green-200'
            : card.recognized_name
            ? 'bg-amber-50 border-amber-200'
            : 'bg-red-50 border-red-200';

          // Status badge
          const badge = card.confirmed_name
            ? { label: 'Confirmed', cls: 'bg-green-500 text-white' }
            : card.recognized_name
            ? { label: `${Math.round((card.match_score ?? 0) * 100)}%`, cls: 'bg-amber-400 text-white' }
            : { label: 'Unknown', cls: 'bg-red-500 text-white' };

          return (
            <li
              key={card.id}
              className={`flex items-center gap-3 border rounded-lg p-3 ${rowClass}`}
            >
              {/* Thumbnail */}
              {card.thumbnail_base64 ? (
                <img
                  src={`data:image/jpeg;base64,${card.thumbnail_base64}`}
                  alt=""
                  className="w-10 h-14 object-cover rounded flex-shrink-0"
                />
              ) : (
                <div className="w-10 h-14 rounded bg-gray-200 flex items-center justify-center text-gray-400 text-xs flex-shrink-0">
                  ?
                </div>
              )}

              {/* Name / edit field */}
              <div className="flex-1 min-w-0">
                {isEditing ? (
                  <input
                    autoFocus
                    className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveEdit(card);
                      if (e.key === 'Escape') cancelEdit();
                    }}
                  />
                ) : (
                  <p className="text-sm font-medium truncate">{card.display_name}</p>
                )}
                {card.raw_ocr_text && !isEditing && (
                  <p className="text-xs text-gray-400 truncate">OCR: {card.raw_ocr_text}</p>
                )}
              </div>

              {/* Badge */}
              <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${badge.cls}`}>
                {badge.label}
              </span>

              {/* Actions */}
              {isEditing ? (
                <div className="flex gap-1 flex-shrink-0">
                  <button
                    onClick={() => saveEdit(card)}
                    disabled={isSaving}
                    className="text-xs bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    {isSaving ? '…' : 'Save'}
                  </button>
                  <button
                    onClick={cancelEdit}
                    className="text-xs bg-gray-200 px-2 py-1 rounded hover:bg-gray-300"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => startEdit(card)}
                  className="text-xs text-blue-600 hover:underline flex-shrink-0"
                >
                  Edit
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

FILEOF

mkdir -p "$FRONTEND/src/components/checkin"
cat > "$FRONTEND/src/components/checkin/CheckinFlow.tsx" << 'FILEOF'
import { useState, FormEvent } from 'react';
import { startCheckin, uploadImage, finalizeCheckin, getAnnotatedImageUrl } from '../../api/checkin';
import { Card, Cube } from '../../types';
import { CardCanvas } from './CardCanvas';
import { CardList } from './CardList';
import { ImageUpload } from './ImageUpload';

type Step = 'details' | 'upload' | 'review' | 'done';

const STEPS: Step[] = ['details', 'upload', 'review', 'done'];
const STEP_LABELS: Record<Step, string> = {
  details: 'Details',
  upload: 'Upload',
  review: 'Review',
  done: 'Done',
};

interface Props {
  tournamentId: number;
  onComplete?: (cube: Cube) => void;
}

export function CheckinFlow({ tournamentId, onComplete }: Props) {
  const [step, setStep] = useState<Step>('details');

  // Session state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [cube, setCube] = useState<Cube | null>(null);
  const [cards, setCards] = useState<Card[]>([]);
  const [annotatedUrl, setAnnotatedUrl] = useState<string | null>(null);

  // UI state
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form fields
  const [ownerName, setOwnerName] = useState('');
  const [ownerEmail, setOwnerEmail] = useState('');
  const [cubeName, setCubeName] = useState('');

  // ── Step 1: submit owner/cube details ─────────────────────
  async function handleDetailsSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await startCheckin({
        tournament_id: tournamentId,
        owner_name: ownerName.trim(),
        owner_email: ownerEmail.trim() || undefined,
        cube_name: cubeName.trim(),
      });
      setSessionId(res.session_id);
      setCube(res.cube);
      setStep('upload');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start check-in');
    } finally {
      setBusy(false);
    }
  }

  // ── Step 2: upload photo + process ────────────────────────
  async function handleImageSelected(file: File) {
    if (!sessionId) return;
    setError(null);
    setBusy(true);
    try {
      const res = await uploadImage(sessionId, file);
      setCards(res.cards);
      // Cache-bust so the browser re-fetches the newly created annotated image
      setAnnotatedUrl(`${getAnnotatedImageUrl(sessionId)}?t=${Date.now()}`);
      setStep('review');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Image processing failed');
    } finally {
      setBusy(false);
    }
  }

  // ── Step 3: finalize ──────────────────────────────────────
  async function handleFinalize() {
    if (!sessionId) return;
    setError(null);
    setBusy(true);
    try {
      const finalized = await finalizeCheckin(sessionId);
      setCube(finalized);
      setStep('done');
      onComplete?.(finalized);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Finalize failed');
    } finally {
      setBusy(false);
    }
  }

  function handleCardUpdated(updated: Card) {
    setCards((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  }

  const identified = cards.filter((c) => c.confirmed_name ?? c.recognized_name).length;
  const currentStepIndex = STEPS.indexOf(step);

  return (
    <div className="max-w-3xl mx-auto p-6">

      {/* Progress bar */}
      <div className="flex items-center gap-2 mb-8">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={[
              'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold',
              i < currentStepIndex ? 'bg-green-500 text-white' :
              i === currentStepIndex ? 'bg-blue-600 text-white' :
              'bg-gray-200 text-gray-400',
            ].join(' ')}>
              {i < currentStepIndex ? '✓' : i + 1}
            </div>
            <span className={`text-sm hidden sm:block ${i === currentStepIndex ? 'text-gray-800 font-medium' : 'text-gray-400'}`}>
              {STEP_LABELS[s]}
            </span>
            {i < STEPS.length - 1 && (
              <div className={`h-0.5 w-6 ${i < currentStepIndex ? 'bg-green-400' : 'bg-gray-200'}`} />
            )}
          </div>
        ))}
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {/* ── Step 1: Details ── */}
      {step === 'details' && (
        <div className="bg-white border rounded-xl p-6 shadow-sm">
          <h2 className="text-xl font-semibold mb-5">Cube details</h2>
          <form onSubmit={handleDetailsSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Owner name <span className="text-red-500">*</span>
              </label>
              <input
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
                placeholder="Alice"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Owner email
              </label>
              <input
                type="email"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={ownerEmail}
                onChange={(e) => setOwnerEmail(e.target.value)}
                placeholder="alice@example.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Cube name <span className="text-red-500">*</span>
              </label>
              <input
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={cubeName}
                onChange={(e) => setCubeName(e.target.value)}
                placeholder="Alice's Powered Cube"
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="w-full bg-blue-600 text-white py-2.5 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {busy ? 'Starting…' : 'Next →'}
            </button>
          </form>
        </div>
      )}

      {/* ── Step 2: Upload ── */}
      {step === 'upload' && (
        <div className="bg-white border rounded-xl p-6 shadow-sm">
          <h2 className="text-xl font-semibold mb-1">Upload a photo</h2>
          <p className="text-gray-500 text-sm mb-6">
            Lay all cards face-up and take one photo. The system will detect and OCR each card name.
          </p>
          {busy ? (
            <div className="text-center py-16">
              <div className="text-4xl animate-spin mb-4">⚙️</div>
              <p className="text-gray-600">Detecting cards…</p>
            </div>
          ) : (
            <ImageUpload onFileSelected={handleImageSelected} />
          )}
        </div>
      )}

      {/* ── Step 3: Review ── */}
      {step === 'review' && (
        <div className="bg-white border rounded-xl p-6 shadow-sm">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h2 className="text-xl font-semibold">Review cards</h2>
              <p className="text-sm text-gray-500 mt-0.5">
                {identified}/{cards.length} identified · click Edit to correct any name
              </p>
            </div>
            <button
              onClick={handleFinalize}
              disabled={busy}
              className="bg-green-600 text-white px-5 py-2 rounded-lg font-medium hover:bg-green-700 disabled:opacity-50 flex-shrink-0"
            >
              {busy ? 'Saving…' : 'Finalise ✓'}
            </button>
          </div>

          {annotatedUrl && (
            <div className="mb-5">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Annotated scan</p>
              <CardCanvas imageUrl={annotatedUrl} />
            </div>
          )}

          <CardList cards={cards} sessionId={sessionId!} onCardUpdated={handleCardUpdated} />
        </div>
      )}

      {/* ── Step 4: Done ── */}
      {step === 'done' && cube && (
        <div className="bg-white border rounded-xl p-10 shadow-sm text-center">
          <div className="text-5xl mb-4">✅</div>
          <h2 className="text-2xl font-bold text-green-700 mb-2">Check-in complete</h2>
          <p className="text-gray-700 mb-1">
            <strong>{cube.cube_name}</strong> — {cube.owner_name}
          </p>
          <p className="text-gray-500 text-sm">
            {cube.total_cards} cards · {cube.cards_confirmed} confirmed
          </p>
        </div>
      )}
    </div>
  );
}

FILEOF

mkdir -p "$FRONTEND/src/components/checkin"
cat > "$FRONTEND/src/components/checkin/ImageUpload.tsx" << 'FILEOF'
import { useRef, useState } from 'react';

interface Props {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
}

export function ImageUpload({ onFileSelected, disabled = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleFile(file: File) {
    if (file.type.startsWith('image/')) {
      onFileSelected(file);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  return (
    <div
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={[
        'border-2 border-dashed rounded-xl p-12 text-center transition-colors',
        dragging
          ? 'border-blue-500 bg-blue-50'
          : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50',
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
      ].join(' ')}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        disabled={disabled}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
          // Reset so the same file can be re-selected if needed
          e.target.value = '';
        }}
      />
      <div className="text-4xl mb-3">📸</div>
      <p className="text-gray-700 font-medium">Drop an image here, or click to browse</p>
      <p className="text-gray-400 text-sm mt-1">JPEG · PNG · WEBP</p>
    </div>
  );
}

FILEOF

mkdir -p "$FRONTEND/src/pages"
cat > "$FRONTEND/src/pages/CheckinPage.tsx" << 'FILEOF'
import { useState, useEffect, FormEvent } from 'react';
import { listTournaments, createTournament } from '../api/tournaments';
import { CheckinFlow } from '../components/checkin/CheckinFlow';
import { Tournament, Cube } from '../types';

type View = 'select-tournament' | 'checkin';

export function CheckinPage() {
  const [view, setView] = useState<View>('select-tournament');
  const [tournaments, setTournaments] = useState<Tournament[]>([]);
  const [activeTournament, setActiveTournament] = useState<Tournament | null>(null);
  const [checkedInCubes, setCheckedInCubes] = useState<Cube[]>([]);

  // Create-tournament form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDate, setNewDate] = useState(new Date().toISOString().slice(0, 10));
  const [newLocation, setNewLocation] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Load existing tournaments on mount
  useEffect(() => {
    listTournaments()
      .then(setTournaments)
      .catch((err: unknown) =>
        setLoadError(err instanceof Error ? err.message : 'Failed to load tournaments')
      );
  }, []);

  async function handleCreateTournament(e: FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCreating(true);
    try {
      const created = await createTournament(newName.trim(), newDate, newLocation.trim() || undefined);
      setTournaments((prev) => [created, ...prev]);
      setActiveTournament(created);
      setShowCreateForm(false);
      setNewName('');
      setNewLocation('');
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create tournament');
    } finally {
      setCreating(false);
    }
  }

  function handleSelectTournament(t: Tournament) {
    setActiveTournament(t);
    setView('checkin');
  }

  function handleCheckinComplete(cube: Cube) {
    setCheckedInCubes((prev) => [cube, ...prev]);
    // Stay on the checkin view so the user can check in another cube
  }

  // ── Tournament selection screen ───────────────────────────
  if (view === 'select-tournament') {
    return (
      <div className="min-h-screen bg-gray-50">
        <header className="bg-white border-b px-6 py-4">
          <h1 className="text-lg font-bold text-gray-800">🎴 Cube Card Tracker</h1>
        </header>

        <main className="max-w-lg mx-auto p-6">
          <h2 className="text-xl font-semibold text-gray-800 mb-1">Select a tournament</h2>
          <p className="text-sm text-gray-500 mb-6">
            Choose an existing tournament or create a new one to begin checking in cubes.
          </p>

          {loadError && (
            <p className="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
              {loadError}
            </p>
          )}

          {/* Existing tournaments */}
          {tournaments.length > 0 && (
            <ul className="space-y-2 mb-6">
              {tournaments.map((t) => (
                <li key={t.id}>
                  <button
                    onClick={() => handleSelectTournament(t)}
                    className="w-full text-left bg-white border border-gray-200 rounded-xl p-4 hover:border-blue-400 hover:bg-blue-50 transition-colors"
                  >
                    <p className="font-medium text-gray-800">{t.name}</p>
                    <p className="text-sm text-gray-500">
                      {t.date}{t.location ? ` · ${t.location}` : ''}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {/* Create new tournament */}
          {showCreateForm ? (
            <div className="bg-white border border-gray-200 rounded-xl p-5">
              <h3 className="font-medium text-gray-800 mb-4">New tournament</h3>
              {createError && (
                <p className="mb-3 text-sm text-red-600">{createError}</p>
              )}
              <form onSubmit={handleCreateTournament} className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    required
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="Friday Night Cube"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Date <span className="text-red-500">*</span>
                  </label>
                  <input
                    required
                    type="date"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={newDate}
                    onChange={(e) => setNewDate(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Location</label>
                  <input
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={newLocation}
                    onChange={(e) => setNewLocation(e.target.value)}
                    placeholder="Game store, city…"
                  />
                </div>
                <div className="flex gap-2 pt-1">
                  <button
                    type="submit"
                    disabled={creating}
                    className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                  >
                    {creating ? 'Creating…' : 'Create'}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setShowCreateForm(false); setCreateError(null); }}
                    className="flex-1 bg-gray-100 text-gray-700 py-2 rounded-lg text-sm font-medium hover:bg-gray-200"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          ) : (
            <button
              onClick={() => setShowCreateForm(true)}
              className="w-full border-2 border-dashed border-gray-300 rounded-xl p-4 text-gray-500 hover:border-blue-400 hover:text-blue-600 transition-colors text-sm font-medium"
            >
              + Create new tournament
            </button>
          )}
        </main>
      </div>
    );
  }

  // ── Check-in screen ───────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-3 flex items-center gap-3">
        <button
          onClick={() => { setView('select-tournament'); setCheckedInCubes([]); }}
          className="text-gray-400 hover:text-gray-700 text-sm"
        >
          ← Tournaments
        </button>
        <span className="text-gray-300">|</span>
        <div>
          <span className="font-semibold text-gray-800">{activeTournament?.name}</span>
          {activeTournament?.location && (
            <span className="text-sm text-gray-400 ml-2">{activeTournament.location}</span>
          )}
        </div>
        {checkedInCubes.length > 0 && (
          <span className="ml-auto text-sm text-gray-500">
            {checkedInCubes.length} cube{checkedInCubes.length !== 1 ? 's' : ''} checked in
          </span>
        )}
      </header>

      {/* Completed cubes summary strip */}
      {checkedInCubes.length > 0 && (
        <div className="bg-green-50 border-b border-green-200 px-6 py-2 flex items-center gap-4 overflow-x-auto">
          {checkedInCubes.map((cube) => (
            <span key={cube.id} className="text-sm text-green-700 whitespace-nowrap">
              ✓ {cube.cube_name} ({cube.total_cards} cards)
            </span>
          ))}
        </div>
      )}

      <CheckinFlow
        tournamentId={activeTournament!.id}
        onComplete={handleCheckinComplete}
      />
    </div>
  );
}

FILEOF

mkdir -p "$FRONTEND/src/types"
cat > "$FRONTEND/src/types/Card.ts" << 'FILEOF'
export interface Card {
  id: number;
  cube_id: number;
  raw_ocr_text: string | null;
  recognized_name: string | null;
  confirmed_name: string | null;
  match_score: number | null;
  status: 'detected' | 'confirmed' | 'drafted' | 'returned';
  display_name: string;
  bbox_x: number;
  bbox_y: number;
  bbox_width: number;
  bbox_height: number;
  polygon_json: number[][];
  thumbnail_base64: string | null;
  created_at: string;
  updated_at: string;
}

FILEOF

mkdir -p "$FRONTEND/src/types"
cat > "$FRONTEND/src/types/Cube.ts" << 'FILEOF'
import { Card } from './Card';

export type CubeStatus =
  | 'pending_checkin'
  | 'checked_in'
  | 'in_use'
  | 'returned'
  | 'flagged';

export interface Cube {
  id: number;
  tournament_id: number;
  owner_name: string;
  owner_email: string | null;
  cube_name: string;
  status: CubeStatus;
  session_id: string | null;
  total_cards: number;
  cards_confirmed: number;
  annotated_image_path: string | null;
  cards?: Card[];
  created_at: string;
  updated_at: string;
}

FILEOF

mkdir -p "$FRONTEND/src/types"
cat > "$FRONTEND/src/types/Tournament.ts" << 'FILEOF'
import { Cube } from './Cube';

export type TournamentStatus = 'draft' | 'active' | 'complete' | 'cancelled';

export interface Tournament {
  id: number;
  name: string;
  date: string;
  location: string | null;
  status: TournamentStatus;
  notes: string | null;
  cubes?: Cube[];
  created_at: string;
  updated_at: string;
}

FILEOF

mkdir -p "$FRONTEND/src/types"
cat > "$FRONTEND/src/types/index.ts" << 'FILEOF'
export * from './Card';
export * from './Cube';
export * from './Tournament';

FILEOF

mkdir -p "$FRONTEND/."
cat > "$FRONTEND/.env.example" << 'FILEOF'
# Copy to .env and adjust as needed.
# Points the frontend at the Flask backend.
API_URL=http://localhost:5000

FILEOF

# Create .env from example if it doesn't already exist
if [[ ! -f "$FRONTEND/.env" ]]; then
    cp "$FRONTEND/.env.example" "$FRONTEND/.env"
    echo "  created frontend/.env from .env.example"
fi
if [[ ! -f "$BACKEND/.env" && -f "$BACKEND/.env.example" ]]; then
    cp "$BACKEND/.env.example" "$BACKEND/.env"
    echo "  created backend/.env from .env.example"
fi

echo ""
echo "✓ All files written."
echo ""
echo "Next steps:"
echo "  cd backend && poetry install"
echo "  cd frontend && npm install"
echo "  ./dev.sh"