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

