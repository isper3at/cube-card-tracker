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

