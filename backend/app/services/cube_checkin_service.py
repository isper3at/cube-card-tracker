"""
Cube check-in service.

Assumptions:
  - Cards are photographed upright (no rotation needed)
  - Cards may be fanned/stacked in columns (only title bar visible per card)
  - Any number of cards per image

Debug output
────────────
Set CHECKIN_DEBUG_DIR env var or pass debug_dir= to constructor.

  <debug_dir>/<image_stem>/
    [all DetectionService pipeline stages — see detection_service.py]
    cards/
      card_00/
        title_strip.jpg       ← raw crop sent to OCR
        title_strip_ocr.jpg   ← after preprocessing
        result.txt            ← raw_ocr | matched name | score | bbox
      card_01/ ...
"""

import base64
import os
import cv2
import numpy as np
import logging
from pathlib import Path
from typing import List, Optional

from ..models import db, Cube, Card, CardStatus, CubeStatus
from .detection_service import DetectionService, BBox
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
        debug_dir: Optional[str] = None,
    ):
        resolved_debug = debug_dir or os.getenv("CHECKIN_DEBUG_DIR")

        self.detection_service = DetectionService(
            min_card_area, max_card_area,
            debug_dir=resolved_debug,
        )
        self.ocr_service = OCRService()
        self.card_db_service = CardDatabaseService(card_db_folder)
        self.upload_folder = Path(upload_folder)
        self.annotated_folder = Path(annotated_folder)
        self.fuzzy_threshold = fuzzy_threshold
        self._debug_dir: Optional[Path] = Path(resolved_debug) if resolved_debug else None

        self.card_db_service.ensure_loaded()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def process_image(self, image_path: str, cube: Cube) -> List[Card]:
        """
        Process an uploaded image containing any number of cards.
        Detection service handles both full-card and fanned/stacked layouts.
        Returns a list of Card instances (not yet committed).
        """
        logger.info(f"Processing image for cube {cube.id}: {image_path}")

        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Could not load image: {image_path}")

        image_name = Path(image_path).name
        boxes: List[BBox] = self.detection_service.detect_cards(
            img, image_name=image_name
        )
        logger.info(f"Detected {len(boxes)} card region(s)")

        # Per-image card debug folder
        card_dbg_root: Optional[Path] = None
        if self._debug_dir:
            stem = Path(image_path).stem.replace(" ", "_")[:60]
            card_dbg_root = self._debug_dir / stem / "cards"
            card_dbg_root.mkdir(parents=True, exist_ok=True)

        cards: List[Card] = []
        for idx, bbox in enumerate(boxes):
            dbg_folder = card_dbg_root / f"card_{idx:02d}" if card_dbg_root else None
            if dbg_folder:
                dbg_folder.mkdir(exist_ok=True)

            card = self._process_card_region(img, bbox, cube.id, dbg_folder)
            if card is not None:
                cards.append(card)

        matched = sum(1 for c in cards if c.recognized_name)
        logger.info(f"Processed {len(cards)} card(s), {matched} matched by OCR")
        return cards

    # ─────────────────────────────────────────────────────────────────────────
    # Card processing
    # ─────────────────────────────────────────────────────────────────────────

    def _process_card_region(
        self,
        img: np.ndarray,
        bbox: BBox,
        cube_id: int,
        dbg: Optional[Path],
    ) -> Optional[Card]:
        """
        Crop the title strip, run OCR, fuzzy match, return a Card.
        The bbox is already cropped to just the title bar by the detection service.
        """
        x, y, w, h = bbox
        img_h, img_w = img.shape[:2]

        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(img_w, x + w)
        y2 = min(img_h, y + h)

        if (x2 - x1) < 10 or (y2 - y1) < 5:
            return None

        title_strip = img[y1:y2, x1:x2]

        if dbg:
            _dbg_save(dbg / "title_strip.jpg", title_strip)

        preprocessed = _preprocess_for_ocr(title_strip)

        if dbg:
            _dbg_save(dbg / "title_strip_ocr.jpg", preprocessed)

        raw_text = self.ocr_service.read_text(preprocessed)
        match_result = None
        if raw_text:
            match_result = self.card_db_service.fuzzy_match(raw_text, self.fuzzy_threshold)

        recognized_name = match_result[0] if match_result else None
        match_score     = match_result[1] if match_result else 0.0

        if dbg:
            (dbg / "result.txt").write_text(
                f"raw_ocr    : {raw_text!r}\n"
                f"recognized : {recognized_name!r}\n"
                f"score      : {match_score:.2f}\n"
                f"bbox       : ({x1},{y1}) {x2-x1}x{y2-y1}\n",
                encoding="utf-8",
            )

        # Polygon as 4-corner rectangle for annotation compatibility
        polygon = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

        return Card(
            cube_id=cube_id,
            raw_ocr_text=raw_text,
            recognized_name=recognized_name,
            match_score=match_score,
            status=CardStatus.DETECTED,
            bbox_x=x1,
            bbox_y=y1,
            bbox_width=x2 - x1,
            bbox_height=y2 - y1,
            polygon_json=polygon,
            thumbnail_base64=_make_thumbnail(title_strip),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Annotation
    # ─────────────────────────────────────────────────────────────────────────

    def render_annotated_image(
        self,
        image_path: str,
        cards: List[Card],
        output_path: str,
    ) -> bool:
        try:
            img = cv2.imread(image_path)
            if img is None:
                return False

            for card in cards:
                x, y = card.bbox_x, card.bbox_y
                x2, y2 = x + card.bbox_width, y + card.bbox_height

                if card.confirmed_name:
                    colour = (34, 197, 94)
                elif card.recognized_name:
                    colour = (251, 191, 36)
                else:
                    colour = (239, 68, 68)

                cv2.rectangle(img, (x, y), (x2, y2), colour, 2)

                name = card.display_name
                font, fs, th = cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1
                (tw, text_h), bl = cv2.getTextSize(name, font, fs, th)
                label_y = max(0, y - 4)
                cv2.rectangle(img, (x, label_y - text_h - bl - 2),
                              (x + tw + 6, label_y + 2), colour, -1)
                text_colour = (30, 30, 30) if colour == (251, 191, 36) else (255, 255, 255)
                cv2.putText(img, name, (x + 3, label_y - bl),
                            font, fs, text_colour, th, cv2.LINE_AA)

            cv2.imwrite(output_path, img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            return True

        except Exception as e:
            logger.error(f"Failed to render annotated image: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def update_card_name(self, card: Card, confirmed_name: str):
        card.confirmed_name = confirmed_name
        card.status         = CardStatus.CONFIRMED
        db.session.commit()

    def finalize_cube(self, cube: Cube):
        cube.status          = CubeStatus.CHECKED_IN
        cube.total_cards     = len(cube.cards)
        cube.cards_confirmed = sum(1 for c in cube.cards if c.confirmed_name)
        db.session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _preprocess_for_ocr(img: np.ndarray) -> np.ndarray:
    """CLAHE + upscale + adaptive threshold for Tesseract."""
    if img.size == 0:
        return img
    h, w = img.shape[:2]
    if h < 60:
        scale = 60 / h
        img = cv2.resize(img, (max(1, int(w * scale)), 60),
                         interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img.copy()
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.fastNlMeansDenoising(gray, h=10)
    binary = cv2.adaptiveThreshold(gray, 255,
                                   cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, blockSize=15, C=8)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)


def _make_thumbnail(img: np.ndarray, max_size: int = 120) -> str:
    try:
        h, w = img.shape[:2]
        if h == 0 or w == 0:
            return ""
        scale = min(max_size / w, max_size / h, 1.0)
        resized = cv2.resize(img,
                             (max(1, int(w * scale)), max(1, int(h * scale))),
                             interpolation=cv2.INTER_AREA)
        _, buf = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return base64.b64encode(buf.tobytes()).decode('utf-8')
    except Exception:
        return ""


def _dbg_save(path: Path, img: np.ndarray) -> None:
    out = img.copy()
    if out.dtype != np.uint8:
        out = cv2.normalize(out, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
    if out.ndim == 2:
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    cv2.imwrite(str(path), out, [cv2.IMWRITE_JPEG_QUALITY, 93])