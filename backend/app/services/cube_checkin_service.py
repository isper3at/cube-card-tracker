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

