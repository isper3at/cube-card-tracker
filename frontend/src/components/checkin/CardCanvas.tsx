import React, {
  useRef,
  useEffect,
  useState,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from 'react';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface CardPolygon {
  id: number;
  polygon_json: number[][];   // [[x,y],[x,y],[x,y],[x,y]]
  bbox_x: number;
  bbox_y: number;
  bbox_width: number;
  bbox_height: number;
  display_name: string;
  recognized_name: string | null;
  confirmed_name: string | null;
  raw_ocr_text: string | null;
  match_score: number;
  status: 'detected' | 'confirmed' | 'drafted' | 'returned';
  thumbnail_base64?: string;
}

interface DrawingBox {
  startX: number;
  startY: number;
  endX: number;
  endY: number;
}

interface CardCanvasProps {
  imageUrl: string;           // URL of the source image
  cards: CardPolygon[];
  selectedCardId: number | null;
  onCardSelect: (id: number | null) => void;
  onRegionDrawn: (bbox: { x: number; y: number; width: number; height: number }) => void;
  isDrawingMode: boolean;     // toggled externally
  highlightUnmatched?: boolean;
}

// ── Colour helpers ────────────────────────────────────────────────────────────

const CARD_COLORS = {
  confirmed: '#22c55e',   // green-500
  recognized: '#f59e0b',  // amber-500
  unmatched: '#ef4444',   // red-500
  selected: '#38bdf8',    // sky-400
};

function cardColor(card: CardPolygon, isSelected: boolean): string {
  if (isSelected) return CARD_COLORS.selected;
  if (card.confirmed_name) return CARD_COLORS.confirmed;
  if (card.recognized_name) return CARD_COLORS.recognized;
  return CARD_COLORS.unmatched;
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// ── Scale helpers ─────────────────────────────────────────────────────────────

interface Scale {
  scaleX: number;
  scaleY: number;
  offsetX: number;
  offsetY: number;
  displayW: number;
  displayH: number;
}

function computeScale(
  naturalW: number,
  naturalH: number,
  canvasW: number,
  canvasH: number,
): Scale {
  const scaleX = canvasW / naturalW;
  const scaleY = canvasH / naturalH;
  const scale = Math.min(scaleX, scaleY);
  const displayW = naturalW * scale;
  const displayH = naturalH * scale;
  const offsetX = (canvasW - displayW) / 2;
  const offsetY = (canvasH - displayH) / 2;
  return { scaleX: scale, scaleY: scale, offsetX, offsetY, displayW, displayH };
}

function imgToCanvas(pt: [number, number], s: Scale): [number, number] {
  return [pt[0] * s.scaleX + s.offsetX, pt[1] * s.scaleY + s.offsetY];
}

function canvasToImg(pt: [number, number], s: Scale): [number, number] {
  return [(pt[0] - s.offsetX) / s.scaleX, (pt[1] - s.offsetY) / s.scaleY];
}

// ── Canvas drawing ────────────────────────────────────────────────────────────

function drawPolygon(
  ctx: CanvasRenderingContext2D,
  poly: number[][],
  color: string,
  scale: Scale,
  filled = false,
) {
  const pts = poly.map((p) => imgToCanvas([p[0], p[1]], scale));
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
  if (filled) {
    ctx.fillStyle = hexToRgba(color, 0.18);
    ctx.fill();
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.5;
  ctx.stroke();
}

function drawLabel(
  ctx: CanvasRenderingContext2D,
  text: string,
  bx: number,
  by: number,
  color: string,
  scale: Scale,
) {
  const [cx, cy] = imgToCanvas([bx, by], scale);
  const displayText = text.length > 28 ? text.slice(0, 26) + '…' : text;

  const fontSize = Math.max(10, Math.min(14, 12 * scale.scaleX));
  ctx.font = `600 ${fontSize}px 'Segoe UI', system-ui, sans-serif`;

  const metrics = ctx.measureText(displayText);
  const tw = metrics.width;
  const th = fontSize;
  const pad = 4;

  const lx = cx;
  const ly = cy - 6;

  // Badge background
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(lx, ly - th - pad * 2, tw + pad * 2, th + pad * 2, 3);
  ctx.fill();

  // Text
  ctx.fillStyle = color === CARD_COLORS.recognized ? '#1c1917' : '#ffffff';
  ctx.fillText(displayText, lx + pad, ly - pad);
}

// ── Component ─────────────────────────────────────────────────────────────────

const CardCanvas = forwardRef<{ redraw: () => void }, CardCanvasProps>(
  (
    {
      imageUrl,
      cards,
      selectedCardId,
      onCardSelect,
      onRegionDrawn,
      isDrawingMode,
      highlightUnmatched = false,
    },
    ref,
  ) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const imageRef = useRef<HTMLImageElement | null>(null);
    const scaleRef = useRef<Scale | null>(null);

    const [drawBox, setDrawBox] = useState<DrawingBox | null>(null);
    const [isDrawing, setIsDrawing] = useState(false);
    const drawStartRef = useRef<{ x: number; y: number } | null>(null);

    // ── Load image ────────────────────────────────────────────────────────────

    useEffect(() => {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        imageRef.current = img;
        resizeAndDraw();
      };
      img.src = imageUrl;
    }, [imageUrl]);

    // ── Resize observer ───────────────────────────────────────────────────────

    const resizeAndDraw = useCallback(() => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      const img = imageRef.current;
      if (!canvas || !container || !img) return;

      const { width, height } = container.getBoundingClientRect();
      canvas.width = width;
      canvas.height = height;

      const scale = computeScale(img.naturalWidth, img.naturalHeight, width, height);
      scaleRef.current = scale;

      redraw(scale);
    }, [cards, selectedCardId, drawBox, highlightUnmatched]);

    useEffect(() => {
      const ro = new ResizeObserver(resizeAndDraw);
      if (containerRef.current) ro.observe(containerRef.current);
      return () => ro.disconnect();
    }, [resizeAndDraw]);

    // ── Redraw whenever deps change ───────────────────────────────────────────

    useEffect(() => {
      if (scaleRef.current) redraw(scaleRef.current);
    }, [cards, selectedCardId, drawBox, highlightUnmatched]);

    function redraw(scale: Scale) {
      const canvas = canvasRef.current;
      const img = imageRef.current;
      if (!canvas || !img) return;
      const ctx = canvas.getContext('2d')!;

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw image fitted to canvas
      ctx.drawImage(
        img,
        scale.offsetX,
        scale.offsetY,
        scale.displayW,
        scale.displayH,
      );

      // Dark overlay when a card is selected (dim others)
      if (selectedCardId !== null) {
        ctx.fillStyle = 'rgba(0,0,0,0.35)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        // Re-draw image just for selected card area
        const sel = cards.find((c) => c.id === selectedCardId);
        if (sel?.polygon_json) {
          ctx.save();
          const pts = sel.polygon_json.map((p) => imgToCanvas([p[0], p[1]], scale));
          ctx.beginPath();
          ctx.moveTo(pts[0][0], pts[0][1]);
          for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
          ctx.closePath();
          ctx.clip();
          ctx.drawImage(img, scale.offsetX, scale.offsetY, scale.displayW, scale.displayH);
          ctx.restore();
        }
      }

      // Draw all card polygons
      for (const card of cards) {
        if (!card.polygon_json || card.polygon_json.length < 3) continue;
        const isSelected = card.id === selectedCardId;
        const color = cardColor(card, isSelected);
        const shouldHighlight = !highlightUnmatched || !card.recognized_name;
        drawPolygon(ctx, card.polygon_json, color, scale, isSelected);
        drawLabel(ctx, card.display_name, card.bbox_x, card.bbox_y, color, scale);
      }

      // Draw active draw-box
      if (drawBox) {
        const [ax, ay] = imgToCanvas([drawBox.startX, drawBox.startY], scale);
        const [bx, by] = imgToCanvas([drawBox.endX, drawBox.endY], scale);
        const w = bx - ax;
        const h = by - ay;
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 3]);
        ctx.strokeRect(ax, ay, w, h);
        ctx.fillStyle = 'rgba(56,189,248,0.08)';
        ctx.fillRect(ax, ay, w, h);
        ctx.setLineDash([]);
      }
    }

    useImperativeHandle(ref, () => ({ redraw: () => scaleRef.current && redraw(scaleRef.current) }));

    // ── Hit-test a click against card polygons ────────────────────────────────

    function hitTest(imgX: number, imgY: number): number | null {
      // Use canvas point-in-polygon
      for (const card of cards) {
        if (!card.polygon_json || card.polygon_json.length < 3) continue;
        if (pointInPolygon([imgX, imgY], card.polygon_json)) return card.id;
      }
      return null;
    }

    function pointInPolygon(pt: number[], poly: number[][]): boolean {
      let inside = false;
      const x = pt[0], y = pt[1];
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const xi = poly[i][0], yi = poly[i][1];
        const xj = poly[j][0], yj = poly[j][1];
        if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
          inside = !inside;
        }
      }
      return inside;
    }

    // ── Mouse events ──────────────────────────────────────────────────────────

    function getImgCoords(e: React.MouseEvent<HTMLCanvasElement>): [number, number] | null {
      const canvas = canvasRef.current;
      const scale = scaleRef.current;
      if (!canvas || !scale) return null;
      const rect = canvas.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      return canvasToImg([cx, cy], scale);
    }

    function handleMouseDown(e: React.MouseEvent<HTMLCanvasElement>) {
      if (!isDrawingMode) return;
      const coords = getImgCoords(e);
      if (!coords) return;
      drawStartRef.current = { x: coords[0], y: coords[1] };
      setIsDrawing(true);
      setDrawBox({ startX: coords[0], startY: coords[1], endX: coords[0], endY: coords[1] });
    }

    function handleMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
      if (!isDrawing || !drawStartRef.current) return;
      const coords = getImgCoords(e);
      if (!coords) return;
      setDrawBox({
        startX: drawStartRef.current.x,
        startY: drawStartRef.current.y,
        endX: coords[0],
        endY: coords[1],
      });
    }

    function handleMouseUp(e: React.MouseEvent<HTMLCanvasElement>) {
      if (!isDrawingMode || !isDrawing || !drawBox) return;
      setIsDrawing(false);
      drawStartRef.current = null;

      const x = Math.min(drawBox.startX, drawBox.endX);
      const y = Math.min(drawBox.startY, drawBox.endY);
      const width = Math.abs(drawBox.endX - drawBox.startX);
      const height = Math.abs(drawBox.endY - drawBox.startY);

      if (width > 20 && height > 20) {
        onRegionDrawn({ x, y, width, height });
      }
      setDrawBox(null);
    }

    function handleClick(e: React.MouseEvent<HTMLCanvasElement>) {
      if (isDrawingMode) return;
      const coords = getImgCoords(e);
      if (!coords) return;
      const hit = hitTest(coords[0], coords[1]);
      onCardSelect(hit);
    }

    // ── Cursor ────────────────────────────────────────────────────────────────

    const cursor = isDrawingMode ? 'crosshair' : 'default';

    return (
      <div
        ref={containerRef}
        style={{ width: '100%', height: '100%', position: 'relative', userSelect: 'none' }}
      >
        <canvas
          ref={canvasRef}
          style={{ display: 'block', cursor }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onClick={handleClick}
        />

        {/* Legend */}
        <div
          style={{
            position: 'absolute',
            bottom: 12,
            right: 12,
            background: 'rgba(15,15,20,0.82)',
            backdropFilter: 'blur(8px)',
            borderRadius: 8,
            padding: '8px 12px',
            display: 'flex',
            flexDirection: 'column',
            gap: 5,
            fontSize: 11,
            color: '#e2e8f0',
            pointerEvents: 'none',
          }}
        >
          <LegendDot color={CARD_COLORS.confirmed} label="Confirmed" />
          <LegendDot color={CARD_COLORS.recognized} label="Auto-matched" />
          <LegendDot color={CARD_COLORS.unmatched} label="Unrecognized" />
          {isDrawingMode && <LegendDot color={CARD_COLORS.selected} label="Draw to add" />}
        </div>

        {isDrawingMode && (
          <div
            style={{
              position: 'absolute',
              top: 12,
              left: '50%',
              transform: 'translateX(-50%)',
              background: 'rgba(56,189,248,0.15)',
              border: '1px solid rgba(56,189,248,0.5)',
              color: '#38bdf8',
              borderRadius: 6,
              padding: '5px 14px',
              fontSize: 12,
              fontWeight: 600,
              letterSpacing: '0.04em',
              pointerEvents: 'none',
            }}
          >
            DRAW MODE — drag to outline a card
          </div>
        )}
      </div>
    );
  },
);

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
      <div
        style={{
          width: 10,
          height: 10,
          borderRadius: 2,
          background: color,
          flexShrink: 0,
        }}
      />
      <span>{label}</span>
    </div>
  );
}

CardCanvas.displayName = 'CardCanvas';
export default CardCanvas;