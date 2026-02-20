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

