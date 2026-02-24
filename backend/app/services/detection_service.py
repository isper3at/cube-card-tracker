"""
Card detection service for fanned/stacked cube layouts.

How it works (derived from analysing a real image of 45 cards):
─────────────────────────────────────────────────────────────────
Cards are laid in columns, fanned vertically so only the title bar
of each card is visible (the bottom card in each column is fully visible).
The background (playmat) is dark; card borders are also dark — which makes
blob/contour detection useless for finding individual cards.

Working strategy:
  1. Find column separators  — dark vertical valleys in the column-mean
     intensity profile (black card borders create these valleys).
  2. Validate each column    — a real card column must be wide enough,
     bright enough, and produce enough title-bar peaks.
  3. Find title-bar rows     — within each validated column strip, bright
     horizontal peaks in the row-mean profile mark each card's title bar.
  4. Crop title strips       — one BBox per peak.
  5. NMS                     — remove duplicate boxes if any column
     produces slightly too many peaks.

Debug output
────────────
Set debug_dir in __init__ or pass it to detect_cards().
Writes to <debug_dir>/<image_stem>/:

  00_original.jpg
  01_gray.jpg
  02_enhanced.jpg
  03_col_profile.jpg           ← column intensity curve + separator lines
  04_col_<N>_row_profile.jpg   ← row intensity curve per column + peak lines
  05_all_title_boxes.jpg       ← final detected title strips on original image
"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from scipy.signal import find_peaks
from scipy.ndimage import uniform_filter1d

logger = logging.getLogger(__name__)

BBox = Tuple[int, int, int, int]   # (x, y, w, h)


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DetectionConfig:
    # ── Column detection ───────────────────────────────────────────────────
    col_valley_prominence: float = 12.0   # min prominence to count as separator
    col_valley_min_distance: int  = 120   # min px between two separators
    col_smooth_window: int        = 20    # smoothing window for col-mean profile

    # A column region must exceed this mean brightness; dark regions (playmat,
    # decorative borders) are skipped.
    col_min_mean_brightness: float = 60.0

    # A real card column must be at least this wide (px).
    col_min_width_px: int = 100

    # A real card column must have at least this many title-bar peaks.
    # Tune down if you expect fewer than 8 cards per column.
    col_min_peaks: int = 8

    # ── Title-bar peak detection ───────────────────────────────────────────
    row_peak_prominence: float = 15.0   # min brightness prominence
    row_peak_min_distance: int  = 50    # min px between two peaks
    row_smooth_window: int      = 8     # smoothing window for row-mean profile

    # ── Title strip geometry ───────────────────────────────────────────────
    title_fraction: float = 0.40   # strip height as fraction of avg inter-peak gap
    title_min_px: int     = 22
    title_max_px: int     = 80
    col_x_padding: int    = 4      # trim left/right of each column before cropping
    peak_top_offset: int  = 8      # px above the peak to start the crop

    # ── NMS ───────────────────────────────────────────────────────────────
    nms_iou_threshold: float = 0.40


# ─────────────────────────────────────────────────────────────────────────────
# Debug writer
# ─────────────────────────────────────────────────────────────────────────────

class _DebugWriter:
    def __init__(self, base_dir: Path, stem: str):
        self.root = base_dir / stem
        self.root.mkdir(parents=True, exist_ok=True)
        logger.info(f"[debug] → {self.root}")

    def save(self, rel: str, img: np.ndarray) -> None:
        out = img.copy()
        if out.dtype != np.uint8:
            out = cv2.normalize(out, None, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
        if out.ndim == 2:
            out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(dest), out, [cv2.IMWRITE_JPEG_QUALITY, 93])

    def save_col_profile(self, rel, profile, separators, img_w):
        plot_h = 300
        plot = np.ones((plot_h, img_w, 3), dtype=np.uint8) * 30
        for x in range(len(profile) - 1):
            y1 = plot_h - int(profile[x] / 255 * (plot_h - 10)) - 5
            y2 = plot_h - int(profile[x + 1] / 255 * (plot_h - 10)) - 5
            cv2.line(plot, (x, y1), (x + 1, y2), (200, 200, 200), 1)
        for sx in separators:
            cv2.line(plot, (sx, 0), (sx, plot_h), (0, 0, 255), 2)
            cv2.putText(plot, str(sx), (sx + 2, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 100, 255), 1)
        self.save(rel, plot)

    def save_row_profile(self, rel, profile, peaks, img_h):
        plot_w = 300
        plot = np.ones((img_h, plot_w, 3), dtype=np.uint8) * 30
        for y in range(len(profile) - 1):
            x1 = int(profile[y] / 255 * (plot_w - 10)) + 5
            x2 = int(profile[y + 1] / 255 * (plot_w - 10)) + 5
            cv2.line(plot, (x1, y), (x2, y + 1), (200, 200, 200), 1)
        for py in peaks:
            cv2.line(plot, (0, py), (plot_w, py), (50, 255, 50), 1)
            cv2.putText(plot, str(py), (5, max(10, py - 2)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (50, 255, 50), 1)
        self.save(rel, plot)

    def save_boxes(self, rel, base, boxes, colour=(50, 255, 50), thickness=2):
        canvas = base.copy()
        for i, (x, y, bw, bh) in enumerate(boxes):
            cv2.rectangle(canvas, (x, y), (x + bw, y + bh), colour, thickness)
            cv2.putText(canvas, str(i), (x + 3, y + bh - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, colour, 1, cv2.LINE_AA)
        self.save(rel, canvas)


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class DetectionService:
    """Detects card title-bar regions from fanned cube photo layouts."""

    def __init__(
        self,
        min_card_area: int = 5000,    # kept for API compatibility, unused
        max_card_area: int = 300000,
        config: Optional[DetectionConfig] = None,
        debug_dir: Optional[str] = None,
    ):
        self.config = config or DetectionConfig()
        self._default_debug_dir: Optional[Path] = (
            Path(debug_dir) if debug_dir else None
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Public
    # ─────────────────────────────────────────────────────────────────────────

    def detect_cards(
        self,
        img: np.ndarray,
        debug_dir: Optional[str] = None,
        image_name: str = "image",
    ) -> List[BBox]:
        """
        Returns (x, y, w, h) title-strip boxes, one per detected card,
        sorted left-to-right across columns, top-to-bottom within each column.
        """
        resolved = (
            debug_dir if debug_dir is not None
            else (str(self._default_debug_dir) if self._default_debug_dir else None)
        )
        dbg: Optional[_DebugWriter] = None
        if resolved:
            stem = Path(image_name).stem.replace(" ", "_")[:60]
            dbg = _DebugWriter(Path(resolved), stem)

        img_h, img_w = img.shape[:2]

        if dbg:
            dbg.save("00_original.jpg", img)

        # ── Preprocessing ──────────────────────────────────────────────────
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if dbg:
            dbg.save("01_gray.jpg", gray)

        enhanced = self._enhance(gray)
        if dbg:
            dbg.save("02_enhanced.jpg", enhanced)

        # ── Step 1: column separators ──────────────────────────────────────
        separators = self._find_col_separators(enhanced)
        col_bounds = [0] + separators + [img_w]
        col_ranges = [
            (col_bounds[i], col_bounds[i + 1])
            for i in range(len(col_bounds) - 1)
        ]

        if dbg:
            col_profile = uniform_filter1d(
                enhanced.mean(axis=0), size=self.config.col_smooth_window
            )
            dbg.save_col_profile("03_col_profile.jpg", col_profile, separators, img_w)
        logger.info(f"[detect] {len(separators)} column separators → {len(col_ranges)} regions")

        # ── Steps 2+3: validate columns, find peaks, build boxes ───────────
        all_boxes: List[BBox] = []
        fallback_title_h: int = self.config.title_min_px

        for col_idx, (cx1, cx2) in enumerate(col_ranges):
            col_width = cx2 - cx1
            if col_width < self.config.col_min_width_px:
                logger.debug(f"[detect] col {col_idx}: skipped — width {col_width}px")
                continue

            x1 = cx1 + self.config.col_x_padding
            x2 = cx2 - self.config.col_x_padding
            strip = enhanced[:, x1:x2]

            # Brightness gate — reject dark playmat / decorative borders
            brightness = float(strip.mean())
            if brightness < self.config.col_min_mean_brightness:
                logger.debug(f"[detect] col {col_idx}: skipped — brightness {brightness:.1f}")
                continue

            row_profile = uniform_filter1d(
                strip.mean(axis=1).astype(float),
                size=self.config.row_smooth_window,
            )
            peaks = self._find_title_peaks(row_profile)

            if dbg:
                dbg.save_row_profile(
                    f"04_col_{col_idx:02d}_row_profile.jpg",
                    row_profile, peaks, img_h,
                )

            # Peak count gate — reject regions without enough card rows
            if len(peaks) < self.config.col_min_peaks:
                logger.debug(f"[detect] col {col_idx}: skipped — {len(peaks)} peaks")
                continue

            logger.info(f"[detect] col {col_idx} (x={x1}..{x2}): {len(peaks)} cards")

            # Title strip height from inter-peak spacing
            if len(peaks) >= 2:
                th = int(np.diff(peaks).mean() * self.config.title_fraction)
                th = max(self.config.title_min_px, min(th, self.config.title_max_px))
                fallback_title_h = th
            else:
                th = fallback_title_h

            for peak_y in peaks:
                ty1 = max(0, peak_y - self.config.peak_top_offset)
                ty2 = min(img_h, ty1 + th)
                all_boxes.append((x1, ty1, x2 - x1, ty2 - ty1))

        # ── NMS ───────────────────────────────────────────────────────────
        all_boxes = self._nms(all_boxes, self.config.nms_iou_threshold)

        # Sort reading-order: left column first, top-to-bottom within each
        all_boxes.sort(key=lambda b: (b[0], b[1]))

        if dbg:
            dbg.save_boxes("05_all_title_boxes.jpg", img, all_boxes)

        logger.info(f"detect_cards → {len(all_boxes)} card(s)")
        return all_boxes

    # ─────────────────────────────────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────────────────────────────────

    def _enhance(self, gray: np.ndarray) -> np.ndarray:
        bilateral = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        return clahe.apply(bilateral)

    def _find_col_separators(self, gray: np.ndarray) -> List[int]:
        col_means = gray.mean(axis=0).astype(float)
        smoothed = uniform_filter1d(col_means, size=self.config.col_smooth_window)
        valleys, _ = find_peaks(
            255.0 - smoothed,
            prominence=self.config.col_valley_prominence,
            distance=self.config.col_valley_min_distance,
        )
        return sorted(valleys.tolist())

    def _find_title_peaks(self, row_profile: np.ndarray) -> List[int]:
        peaks, _ = find_peaks(
            row_profile,
            prominence=self.config.row_peak_prominence,
            distance=self.config.row_peak_min_distance,
        )
        return self._prune_peaks(sorted(peaks.tolist()))

    @staticmethod
    def _prune_peaks(peaks: List[int], max_gap_factor: float = 1.55) -> List[int]:
        """
        Remove spurious peaks caused by the bottom card being fully visible
        and generating secondary brightness peaks below its title bar.

        Strategy: compute the median inter-peak gap using only the smallest
        75% of gaps (robust against the one large gap before the bottom card).
        Then walk through peaks and stop as soon as a gap exceeds
        median * max_gap_factor (the bottom-card outlier).
        Peaks that are too close together (< 55% of median) are also dropped.
        """
        if len(peaks) < 3:
            return peaks

        gaps = np.diff(peaks)
        # Use lower quartile of gaps as the "typical" spacing
        q75 = float(np.percentile(gaps, 75))
        core = gaps[gaps <= q75]
        median_gap = float(np.median(core)) if len(core) else float(np.median(gaps))

        result = [peaks[0]]
        for i in range(1, len(peaks)):
            gap = peaks[i] - peaks[i - 1]
            if gap > median_gap * max_gap_factor:
                break      # bottom-card artifact — stop here
            if gap < median_gap * 0.55:
                continue   # too close — duplicate
            result.append(peaks[i])
        return result

    def _nms(self, boxes: List[BBox], iou_thresh: float) -> List[BBox]:
        if not boxes:
            return []
        order = sorted(range(len(boxes)),
                       key=lambda i: boxes[i][2] * boxes[i][3], reverse=True)
        kept, suppressed = [], set()
        for i in order:
            if i in suppressed:
                continue
            kept.append(i)
            x1, y1, w1, h1 = boxes[i]
            for j in order:
                if j in suppressed or j == i:
                    continue
                x2, y2, w2, h2 = boxes[j]
                ix1, iy1 = max(x1, x2), max(y1, y2)
                ix2, iy2 = min(x1 + w1, x2 + w2), min(y1 + h1, y2 + h2)
                if ix2 <= ix1 or iy2 <= iy1:
                    continue
                inter = (ix2 - ix1) * (iy2 - iy1)
                union = w1 * h1 + w2 * h2 - inter
                if union > 0 and inter / union >= iou_thresh:
                    suppressed.add(j)
        return [boxes[i] for i in kept]