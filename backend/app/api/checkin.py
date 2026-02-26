"""
Cube check-in API endpoints.

URL patterns supported (inferred from frontend behaviour):
  POST /api/checkin/start                              → create cube + session
  POST /api/checkin/<session_id>/upload                → upload image, run detection
  GET  /api/checkin/<session_id>                       → get session state + cards
  POST /api/checkin/<session_id>/detect-region         → detect card in user-drawn bbox
  PATCH  /api/checkin/<session_id>/cards/<card_id>     → confirm/edit card name
  DELETE /api/checkin/<session_id>/cards/<card_id>     → remove a card
  POST /api/checkin/<session_id>/finalize              → mark cube checked-in

  # Also keep /upload and /detect-region without session prefix for direct cube_id use
  POST /api/checkin/upload                             → alt upload (cube_id in form)
  POST /api/checkin/detect-region                      → alt detect (cube_id in body)
  PATCH  /api/checkin/cards/<card_id>                  → alt card edit
  DELETE /api/checkin/cards/<card_id>                  → alt card delete

  GET  /api/checkin/images/annotated/<filename>
  GET  /api/checkin/images/upload/<filename>
"""
import os
import uuid
import logging
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from werkzeug.utils import secure_filename

from ..models import db, Cube, Card, CardStatus, CubeStatus
from ..services.cube_checkin_service import CubeCheckinService

logger = logging.getLogger(__name__)
bp = Blueprint('checkin', __name__, url_prefix='/api/checkin')

ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}


def _allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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


def _get_cube_by_session(session_id: str) -> Cube:
    cube = Cube.query.filter_by(session_id=session_id).first()
    if cube is None:
        from flask import abort
        abort(404, description=f"No cube found for session {session_id}")
    return cube


# ─────────────────────────────────────────────────────────────────────────────
# START
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/start', methods=['POST'])
def start_checkin():
    """
    POST /api/checkin/start
    JSON: { tournament_id, owner_name, owner_email, cube_name }
    """
    data = request.get_json(force=True) or {}

    tournament_id = data.get('tournament_id')
    owner_name = data.get('owner_name', 'Unknown')
    owner_email = data.get('owner_email', '')
    cube_name = data.get('cube_name', 'My Cube')

    if not tournament_id:
        return jsonify({'error': 'tournament_id is required'}), 400

    session_id = uuid.uuid4().hex

    cube = Cube(
        tournament_id=tournament_id,
        owner_name=owner_name,
        owner_email=owner_email,
        cube_name=cube_name,
        status=CubeStatus.PENDING_CHECKIN,
        session_id=session_id,
    )
    db.session.add(cube)
    db.session.commit()

    return jsonify({
        'cube_id': cube.id,
        'session_id': session_id,
        'cube': cube.to_dict(),
    }), 201


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/<session_id>', methods=['GET'])
def get_session(session_id: str):
    """GET /api/checkin/<session_id>"""
    cube = _get_cube_by_session(session_id)
    return jsonify({
        'cube': cube.to_dict(),
        'cards': [c.to_dict() for c in cube.cards],
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# UPLOAD  (session-scoped + legacy direct)
# ─────────────────────────────────────────────────────────────────────────────

def _handle_upload(cube: Cube) -> dict:
    """Shared upload logic given a resolved Cube instance."""
    if 'file' not in request.files:
        return None, ('No file provided', 400)

    file = request.files['file']
    if not file or not _allowed_file(file.filename):
        return None, ('Invalid file type', 400)

    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    file.save(image_path)

    cube.source_image_path = image_path
    db.session.commit()

    svc = _get_service()
    cards = svc.process_image(image_path, cube)

    for card in cards:
        db.session.add(card)
    db.session.commit()

    os.makedirs(current_app.config['ANNOTATED_FOLDER'], exist_ok=True)
    ann_filename = f"ann_{filename}"
    ann_path = os.path.join(current_app.config['ANNOTATED_FOLDER'], ann_filename)
    svc.render_annotated_image(image_path, cards, ann_path)
    cube.annotated_image_path = ann_path
    db.session.commit()

    return {
        'cube_id': cube.id,
        'session_id': cube.session_id,
        'image_filename': filename,
        'cards': [c.to_dict() for c in cards],
        'total_detected': len(cards),
    }, None


@bp.route('/<session_id>/upload', methods=['POST'])
def upload_image_session(session_id: str):
    """POST /api/checkin/<session_id>/upload"""
    cube = _get_cube_by_session(session_id)
    try:
        result, err = _handle_upload(cube)
        if err:
            return jsonify({'error': err[0]}), err[1]
        return jsonify(result), 200
    except Exception as e:
        logger.exception("upload error")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/upload', methods=['POST'])
def upload_image_direct():
    """POST /api/checkin/upload  (cube_id in form data)"""
    cube_id = request.form.get('cube_id', type=int)
    cube = Cube.query.get(cube_id) if cube_id else None
    if cube is None:
        return jsonify({'error': 'Cube not found'}), 404
    try:
        result, err = _handle_upload(cube)
        if err:
            return jsonify({'error': err[0]}), err[1]
        return jsonify(result), 200
    except Exception as e:
        logger.exception("upload error")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# DETECT REGION  (session-scoped + legacy direct)
# ─────────────────────────────────────────────────────────────────────────────

def _handle_detect_region(cube: Cube, bbox: dict):
    """Shared detect-region logic."""
    import cv2
    import numpy as np
    from ..services.detection_service import DetectionService
    from ..services.ocr_service import OCRService
    from ..services.card_db_service import CardDatabaseService

    if not cube.source_image_path:
        return None, ('No image uploaded for this cube yet', 422)

    cfg = current_app.config
    img = cv2.imread(cube.source_image_path)
    if img is None:
        return None, ('Cannot read source image', 500)

    det = DetectionService(1000, 500000)
    rect = det.detect_card_in_region(img, bbox)
    if rect is None:
        return None, ('No card found in region', 422)

    polygon = det.rect_to_polygon(rect)

    box = np.array(polygon, dtype=np.int32)
    bx, by, bw, bh = cv2.boundingRect(box)
    h_img, w_img = img.shape[:2]
    bx = max(0, bx); by = max(0, by)
    bx2 = min(w_img, bx + bw); by2 = min(h_img, by + bh)
    crop = img[by:by2, bx:bx2]

    from ..services.ocr_service import OCRService
    ocr = OCRService()
    name_h = min(int(bh * 0.3), 120)
    raw_text = ocr.read_text(crop[:name_h, :]) if crop.size > 0 else ''

    card_db = CardDatabaseService(cfg['CARD_DB_FOLDER'])
    card_db.ensure_loaded()
    match_result = card_db.fuzzy_match(raw_text, cfg.get('FUZZY_MATCH_THRESHOLD', 70)) if raw_text else None

    recognized_name = match_result[0] if match_result else None
    match_score = float(match_result[1]) if match_result else 0.0

    svc = _get_service()
    thumb = svc._create_thumbnail(crop)

    card = Card(
        cube_id=cube.id,
        raw_ocr_text=raw_text,
        recognized_name=recognized_name,
        match_score=match_score,
        status=CardStatus.DETECTED,
        bbox_x=bx,
        bbox_y=by,
        bbox_width=bw,
        bbox_height=bh,
        polygon_json=polygon,
        thumbnail_base64=thumb,
    )
    db.session.add(card)
    db.session.commit()
    return card, None


@bp.route('/<session_id>/detect-region', methods=['POST'])
def detect_region_session(session_id: str):
    """POST /api/checkin/<session_id>/detect-region"""
    cube = _get_cube_by_session(session_id)
    data = request.get_json(force=True) or {}
    bbox = data.get('bbox')
    if not bbox:
        return jsonify({'error': 'bbox required'}), 400
    try:
        card, err = _handle_detect_region(cube, bbox)
        if err:
            return jsonify({'error': err[0]}), err[1]
        return jsonify({'card': card.to_dict()}), 200
    except Exception as e:
        logger.exception("detect-region error")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/detect-region', methods=['POST'])
def detect_region_direct():
    """POST /api/checkin/detect-region  (cube_id in body)"""
    data = request.get_json(force=True) or {}
    cube_id = data.get('cube_id')
    bbox = data.get('bbox')
    if not cube_id or not bbox:
        return jsonify({'error': 'cube_id and bbox required'}), 400
    cube = Cube.query.get(cube_id)
    if cube is None:
        return jsonify({'error': 'Cube not found'}), 404
    try:
        card, err = _handle_detect_region(cube, bbox)
        if err:
            return jsonify({'error': err[0]}), err[1]
        return jsonify({'card': card.to_dict()}), 200
    except Exception as e:
        logger.exception("detect-region error")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# CARD CRUD  (session-scoped + legacy direct)
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_card(card_id: int, session_id: str = None) -> Card:
    card = Card.query.get(card_id)
    if card is None:
        from flask import abort
        abort(404, description=f"Card {card_id} not found")
    if session_id:
        cube = _get_cube_by_session(session_id)
        if card.cube_id != cube.id:
            from flask import abort
            abort(403, description="Card does not belong to this session")
    return card


@bp.route('/<session_id>/cards/<int:card_id>', methods=['PATCH'])
def update_card_session(session_id: str, card_id: int):
    """PATCH /api/checkin/<session_id>/cards/<card_id>"""
    card = _resolve_card(card_id, session_id)
    data = request.get_json(force=True) or {}
    if 'confirmed_name' in data:
        _get_service().update_card_name(card, data['confirmed_name'])
    return jsonify({'card': card.to_dict()}), 200


@bp.route('/<session_id>/cards/<int:card_id>', methods=['DELETE'])
def delete_card_session(session_id: str, card_id: int):
    """DELETE /api/checkin/<session_id>/cards/<card_id>"""
    card = _resolve_card(card_id, session_id)
    db.session.delete(card)
    db.session.commit()
    return jsonify({'deleted': card_id}), 200


@bp.route('/cards/<int:card_id>', methods=['PATCH'])
def update_card_direct(card_id: int):
    """PATCH /api/checkin/cards/<card_id>"""
    card = _resolve_card(card_id)
    data = request.get_json(force=True) or {}
    if 'confirmed_name' in data:
        _get_service().update_card_name(card, data['confirmed_name'])
    return jsonify({'card': card.to_dict()}), 200


@bp.route('/cards/<int:card_id>', methods=['DELETE'])
def delete_card_direct(card_id: int):
    """DELETE /api/checkin/cards/<card_id>"""
    card = _resolve_card(card_id)
    db.session.delete(card)
    db.session.commit()
    return jsonify({'deleted': card_id}), 200


# ─────────────────────────────────────────────────────────────────────────────
# FINALIZE  (session-scoped + legacy)
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/<session_id>/finalize', methods=['POST'])
def finalize_session(session_id: str):
    """POST /api/checkin/<session_id>/finalize"""
    cube = _get_cube_by_session(session_id)
    _get_service().finalize_cube(cube)
    return jsonify({'cube': cube.to_dict()}), 200


@bp.route('/cubes/<int:cube_id>/finalize', methods=['POST'])
def finalize_direct(cube_id: int):
    """POST /api/checkin/cubes/<cube_id>/finalize"""
    cube = Cube.query.get_or_404(cube_id)
    _get_service().finalize_cube(cube)
    return jsonify({'cube': cube.to_dict()}), 200


# ─────────────────────────────────────────────────────────────────────────────
# IMAGE SERVING
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/images/annotated/<path:filename>')
def serve_annotated(filename: str):
    return send_from_directory(current_app.config['ANNOTATED_FOLDER'], filename)


@bp.route('/images/upload/<path:filename>')
def serve_upload(filename: str):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)