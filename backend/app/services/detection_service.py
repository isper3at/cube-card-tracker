"""
Card detection service using contour detection to find full card polygons.
"""
import cv2
import numpy as np
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Simple type alias kept for backwards-compatibility with cube_checkin_service
BBox = dict  # {x, y, width, height}


class DetectionService:
    """Detects Magic card regions in images using contour analysis."""

    def __init__(self, min_card_area: int = 5000, max_card_area: int = 300000):
        self.min_card_area = min_card_area
        self.max_card_area = max_card_area

    def detect_cards(self, img: np.ndarray) -> List[Tuple]:
        """
        Detect card regions and return rotated rectangles (minAreaRect tuples).
        Each rect is ((cx, cy), (w, h), angle).
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Gentle blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Adaptive threshold to handle varied lighting
        thresh = cv2.adaptiveThreshold(
            blurred, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=15,
            C=4
        )

        # Morphological closing to connect card edges
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        rects = []
        img_area = img.shape[0] * img.shape[1]

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_card_area or area > self.max_card_area:
                continue

            # Fit a rotated rectangle around the contour
            rect = cv2.minAreaRect(cnt)
            (cx, cy), (rw, rh), angle = rect

            # Ensure portrait (height > width)
            if rw > rh:
                rw, rh = rh, rw
                angle = (angle + 90) % 180

            # Filter by aspect ratio: MTG cards are 2.5" x 3.5" ≈ 0.714
            aspect = rw / rh if rh > 0 else 0
            if not (0.55 < aspect < 0.85):
                continue

            rects.append(((cx, cy), (rw, rh), angle))

        logger.info(f"detect_cards: found {len(rects)} candidates from {len(contours)} contours")
        return rects

    def detect_card_in_region(self, img: np.ndarray, bbox: dict) -> Tuple:
        """
        Given a user-drawn bounding box (x, y, width, height in image coords),
        detect the card within that region and return a rotated rect for the
        full card polygon.

        Returns a rotated rect tuple ((cx, cy), (w, h), angle) in full-image coords,
        or None if nothing suitable is found.
        """
        x = int(bbox['x'])
        y = int(bbox['y'])
        w = int(bbox['width'])
        h = int(bbox['height'])

        x = max(0, x)
        y = max(0, y)
        x2 = min(img.shape[1], x + w)
        y2 = min(img.shape[0], y + h)

        roi = img[y:y2, x:x2]
        if roi.size == 0:
            return None

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2.adaptiveThreshold(
            blurred, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=15,
            C=4
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best = None
        best_area = 0

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 1000:
                continue
            if area > best_area:
                best_area = area
                best = cnt

        if best is None:
            # Fall back: use the whole ROI as the rect
            cx_local = w / 2
            cy_local = h / 2
            rect_local = ((cx_local, cy_local), (float(w), float(h)), 0.0)
        else:
            rect_local = cv2.minAreaRect(best)

        # Translate back to full-image coordinates
        (lcx, lcy), (lw, lh), angle = rect_local
        full_cx = lcx + x
        full_cy = lcy + y

        return ((full_cx, full_cy), (lw, lh), angle)

    def rect_to_polygon(self, rect) -> List[List[int]]:
        """Convert a rotated rect to a 4-point polygon in full-image coords."""
        box = cv2.boxPoints(rect)
        box = np.int32(box)
        return box.tolist()