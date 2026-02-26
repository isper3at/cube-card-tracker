"""
Cube check-in API endpoints.
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


# ── Upload & auto-detect ──────────────────────────────────────────────────────

@bp.route('/upload', methods=['POST'])
def upload_image():
    """
    POST /api/checkin/upload
    Multipart: file=<image>, cube_id=<int>

    Runs full auto-detection on the image and returns detected cards with
    polygons + OCR titles.
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    cube_id = request.form.get('cube_id', type=int)

    if not file or not _allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400

    cube = Cube.query.get(cube_id) if cube_id else None
    if cube is None:
        return jsonify({'error': 'Cube not found'}), 404

    # Save uploaded file
    os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
    filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    file.save(image_path)

    cube.source_image_path = image_path
    db.session.commit()

    try:
        svc = _get_service()
        cards = svc.process_image(image_path, cube)

        # Persist cards
        for card in cards:
            db.session.add(card)
        db.session.commit()

        # Render annotated image
        os.makedirs(current_app.config['ANNOTATED_FOLDER'], exist_ok=True)
        ann_filename = f"ann_{filename}"
        ann_path = os.path.join(current_app.config['ANNOTATED_FOLDER'], ann_filename)
        svc.render_annotated_image(image_path, cards, ann_path)
        cube.annotated_image_path = ann_path
        db.session.commit()

        return jsonify({
            'cube_id': cube.id,
            'image_filename': filename,
            'cards': [c.to_dict() for c in cards],
            'total_detected': len(cards),
        }), 200

    except Exception as e:
        logger.exception("Error processing image")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ── Detect card within a user-drawn region ────────────────────────────────────

@bp.route('/detect-region', methods=['POST'])
def detect_region():
    """
    POST /api/checkin/detect-region
    JSON: { cube_id, bbox: {x, y, width, height} }

    Detects the card inside the user-drawn bbox, runs OCR on it, and
    returns a new Card (unsaved) with polygon + title.
    """
    data = request.get_json(force=True)
    cube_id = data.get('cube_id')
    bbox = data.get('bbox')  # {x, y, width, height} in original image pixels

    if not cube_id or not bbox:
        return jsonify({'error': 'cube_id and bbox required'}), 400

    cube = Cube.query.get(cube_id)
    if cube is None or not cube.source_image_path:
        return jsonify({'error': 'Cube not found or no image uploaded yet'}), 404

    try:
        import cv2
        import numpy as np
        from ..services.detection_service import DetectionService
        from ..services.ocr_service import OCRService
        from ..services.card_db_service import CardDatabaseService

        cfg = current_app.config
        img = cv2.imread(cube.source_image_path)
        if img is None:
            return jsonify({'error': 'Cannot read source image'}), 500

        det = DetectionService(cfg.get('MIN_CARD_AREA', 1000), cfg.get('MAX_CARD_AREA', 500000))
        rect = det.detect_card_in_region(img, bbox)
        if rect is None:
            return jsonify({'error': 'No card found in region'}), 422

        polygon = det.rect_to_polygon(rect)

        # Crop for OCR
        (cx, cy), (rw, rh), angle = rect
        box = np.array(polygon, dtype=np.int32)
        bx, by, bw, bh = cv2.boundingRect(box)
        h_img, w_img = img.shape[:2]
        bx = max(0, bx); by = max(0, by)
        bx2 = min(w_img, bx + bw); by2 = min(h_img, by + bh)
        crop = img[by:by2, bx:bx2]

        ocr = OCRService()
        name_h = min(int(bh * 0.3), 120)
        raw_text = ocr.read_text(crop[:name_h, :]) if crop.size > 0 else ''

        card_db = CardDatabaseService(cfg['CARD_DB_FOLDER'])
        card_db.ensure_loaded()
        match_result = card_db.fuzzy_match(raw_text, cfg.get('FUZZY_MATCH_THRESHOLD', 70)) if raw_text else None

        recognized_name = match_result[0] if match_result else None
        match_score = match_result[1] if match_result else 0.0

        # Thumbnail
        svc = _get_service()
        thumb = svc._create_thumbnail(crop)

        card = Card(
            cube_id=cube_id,
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

        return jsonify({'card': card.to_dict()}), 200

    except Exception as e:
        logger.exception("detect-region error")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ── Card CRUD ─────────────────────────────────────────────────────────────────

@bp.route('/cards/<int:card_id>', methods=['PATCH'])
def update_card(card_id: int):
    """PATCH /api/checkin/cards/<id>  — confirm/edit a card name."""
    card = Card.query.get_or_404(card_id)
    data = request.get_json(force=True)

    if 'confirmed_name' in data:
        svc = _get_service()
        svc.update_card_name(card, data['confirmed_name'])

    return jsonify({'card': card.to_dict()}), 200


@bp.route('/cards/<int:card_id>', methods=['DELETE'])
def delete_card(card_id: int):
    """DELETE /api/checkin/cards/<id>"""
    card = Card.query.get_or_404(card_id)
    db.session.delete(card)
    db.session.commit()
    return jsonify({'deleted': card_id}), 200


@bp.route('/cubes/<int:cube_id>/finalize', methods=['POST'])
def finalize(cube_id: int):
    """POST /api/checkin/cubes/<id>/finalize"""
    cube = Cube.query.get_or_404(cube_id)
    svc = _get_service()
    svc.finalize_cube(cube)
    return jsonify({'cube': cube.to_dict()}), 200


# ── Image serving ─────────────────────────────────────────────────────────────

@bp.route('/images/annotated/<path:filename>')
def serve_annotated(filename: str):
    return send_from_directory(current_app.config['ANNOTATED_FOLDER'], filename)


@bp.route('/images/upload/<path:filename>')
def serve_upload(filename: str):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)