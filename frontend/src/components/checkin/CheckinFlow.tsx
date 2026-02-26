import React, { useState, useRef, useCallback } from 'react';
import CardCanvas, { CardPolygon } from './CardCanvas';

// ── API helpers ───────────────────────────────────────────────────────────────

const API = import.meta.env.VITE_API_URL ?? '';

async function uploadImage(cubeId: number, file: File): Promise<{ cards: CardPolygon[]; image_filename: string }> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('cube_id', String(cubeId));
  const res = await fetch(`${API}/api/checkin/upload`, { method: 'POST', body: fd });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function detectRegion(
  cubeId: number,
  bbox: { x: number; y: number; width: number; height: number },
): Promise<{ card: CardPolygon }> {
  const res = await fetch(`${API}/api/checkin/detect-region`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cube_id: cubeId, bbox }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function confirmCard(cardId: number, name: string): Promise<{ card: CardPolygon }> {
  const res = await fetch(`${API}/api/checkin/cards/${cardId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirmed_name: name }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function deleteCard(cardId: number): Promise<void> {
  await fetch(`${API}/api/checkin/cards/${cardId}`, { method: 'DELETE' });
}

// ── Component ─────────────────────────────────────────────────────────────────

interface CheckinFlowProps {
  cubeId: number;
}

type Status = 'idle' | 'uploading' | 'detecting' | 'ready' | 'error';

export default function CheckinFlow({ cubeId }: CheckinFlowProps) {
  const [status, setStatus] = useState<Status>('idle');
  const [cards, setCards] = useState<CardPolygon[]>([]);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [selectedCardId, setSelectedCardId] = useState<number | null>(null);
  const [isDrawingMode, setIsDrawingMode] = useState(false);
  const [editName, setEditName] = useState('');
  const [editingId, setEditingId] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [pendingRegion, setPendingRegion] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Upload handler ────────────────────────────────────────────────────────

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setStatus('uploading');
    setErrorMsg('');

    // Preview URL
    const url = URL.createObjectURL(file);
    setImageUrl(url);

    try {
      const result = await uploadImage(cubeId, file);
      setCards(result.cards);
      setStatus('ready');
    } catch (err: any) {
      setErrorMsg(err.message ?? 'Upload failed');
      setStatus('error');
    }
  }, [cubeId]);

  // ── Region drawn by user ──────────────────────────────────────────────────

  const handleRegionDrawn = useCallback(async (bbox: { x: number; y: number; width: number; height: number }) => {
    setIsDrawingMode(false);
    setPendingRegion(true);
    try {
      const result = await detectRegion(cubeId, bbox);
      setCards((prev) => [...prev, result.card]);
      setSelectedCardId(result.card.id);
    } catch (err: any) {
      setErrorMsg(`Region detection failed: ${err.message}`);
    } finally {
      setPendingRegion(false);
    }
  }, [cubeId]);

  // ── Confirm / edit card ───────────────────────────────────────────────────

  const startEdit = (card: CardPolygon) => {
    setEditingId(card.id);
    setEditName(card.confirmed_name ?? card.recognized_name ?? card.raw_ocr_text ?? '');
  };

  const saveEdit = async () => {
    if (!editingId) return;
    try {
      const result = await confirmCard(editingId, editName);
      setCards((prev) => prev.map((c) => (c.id === editingId ? result.card : c)));
      setEditingId(null);
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  const removeCard = async (cardId: number) => {
    await deleteCard(cardId);
    setCards((prev) => prev.filter((c) => c.id !== cardId));
    if (selectedCardId === cardId) setSelectedCardId(null);
  };

  // ── Selected card ─────────────────────────────────────────────────────────

  const selectedCard = cards.find((c) => c.id === selectedCardId) ?? null;

  const confirmed = cards.filter((c) => c.confirmed_name).length;
  const matched = cards.filter((c) => c.recognized_name && !c.confirmed_name).length;
  const unmatched = cards.filter((c) => !c.recognized_name).length;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={styles.root}>
      {/* ── Header ── */}
      <div style={styles.header}>
        <h2 style={styles.title}>Cube Check-in</h2>
        <div style={styles.headerActions}>
          {imageUrl && (
            <>
              <button
                style={{
                  ...styles.btn,
                  ...(isDrawingMode ? styles.btnActive : styles.btnOutline),
                }}
                onClick={() => setIsDrawingMode((v) => !v)}
                title="Toggle draw mode to manually add a card region"
              >
                {isDrawingMode ? '✏️ Drawing…' : '+ Add Region'}
              </button>
              <button
                style={{ ...styles.btn, ...styles.btnOutline }}
                onClick={() => fileInputRef.current?.click()}
              >
                Re-upload
              </button>
            </>
          )}
          {!imageUrl && (
            <button
              style={{ ...styles.btn, ...styles.btnPrimary }}
              onClick={() => fileInputRef.current?.click()}
            >
              Upload Image
            </button>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={handleFileChange}
          />
        </div>
      </div>

      {/* ── Stats bar ── */}
      {cards.length > 0 && (
        <div style={styles.statsBar}>
          <StatChip color="#22c55e" label={`${confirmed} confirmed`} />
          <StatChip color="#f59e0b" label={`${matched} auto-matched`} />
          <StatChip color="#ef4444" label={`${unmatched} unrecognized`} />
          <StatChip color="#94a3b8" label={`${cards.length} total`} />
          {pendingRegion && <StatChip color="#38bdf8" label="Detecting…" pulse />}
        </div>
      )}

      {/* ── Error ── */}
      {errorMsg && (
        <div style={styles.errorBanner}>
          ⚠ {errorMsg}
          <button style={styles.dismissBtn} onClick={() => setErrorMsg('')}>×</button>
        </div>
      )}

      {/* ── Main layout ── */}
      <div style={styles.body}>
        {/* Canvas */}
        <div style={styles.canvasWrap}>
          {status === 'uploading' && (
            <div style={styles.overlay}>
              <Spinner />
              <span>Processing image…</span>
            </div>
          )}
          {!imageUrl && status === 'idle' && (
            <div style={styles.emptyState} onClick={() => fileInputRef.current?.click()}>
              <div style={styles.emptyIcon}>🃏</div>
              <div style={styles.emptyText}>Click or drag an image of your cube here</div>
            </div>
          )}
          {imageUrl && (
            <CardCanvas
              imageUrl={imageUrl}
              cards={cards}
              selectedCardId={selectedCardId}
              onCardSelect={setSelectedCardId}
              onRegionDrawn={handleRegionDrawn}
              isDrawingMode={isDrawingMode}
            />
          )}
        </div>

        {/* Sidebar */}
        <div style={styles.sidebar}>
          {/* Selected card detail */}
          {selectedCard && (
            <div style={styles.cardDetail}>
              <div style={styles.cardDetailHeader}>
                <span style={styles.cardDetailTitle}>Selected Card</span>
                <button style={styles.closeBtn} onClick={() => setSelectedCardId(null)}>×</button>
              </div>

              {selectedCard.thumbnail_base64 && (
                <img
                  src={`data:image/jpeg;base64,${selectedCard.thumbnail_base64}`}
                  alt={selectedCard.display_name}
                  style={styles.thumbnail}
                />
              )}

              <div style={styles.fieldRow}>
                <span style={styles.fieldLabel}>OCR Text</span>
                <span style={styles.fieldValue}>{selectedCard.raw_ocr_text || '—'}</span>
              </div>
              <div style={styles.fieldRow}>
                <span style={styles.fieldLabel}>Matched</span>
                <span style={{ ...styles.fieldValue, color: selectedCard.recognized_name ? '#f59e0b' : '#ef4444' }}>
                  {selectedCard.recognized_name || 'No match'}{' '}
                  {selectedCard.match_score ? `(${Math.round(selectedCard.match_score)}%)` : ''}
                </span>
              </div>
              <div style={styles.fieldRow}>
                <span style={styles.fieldLabel}>Confirmed</span>
                <span style={{ ...styles.fieldValue, color: '#22c55e' }}>
                  {selectedCard.confirmed_name || '—'}
                </span>
              </div>

              {editingId === selectedCard.id ? (
                <div style={styles.editRow}>
                  <input
                    style={styles.editInput}
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && saveEdit()}
                    autoFocus
                    placeholder="Card name…"
                  />
                  <button style={{ ...styles.btn, ...styles.btnPrimary }} onClick={saveEdit}>Save</button>
                  <button style={{ ...styles.btn, ...styles.btnOutline }} onClick={() => setEditingId(null)}>Cancel</button>
                </div>
              ) : (
                <div style={styles.cardActions}>
                  <button style={{ ...styles.btn, ...styles.btnPrimary }} onClick={() => startEdit(selectedCard)}>
                    ✏️ Edit Name
                  </button>
                  <button
                    style={{ ...styles.btn, background: '#7f1d1d', color: '#fca5a5', border: '1px solid #991b1b' }}
                    onClick={() => removeCard(selectedCard.id)}
                  >
                    🗑 Remove
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Card list */}
          <div style={styles.listHeader}>
            <span style={styles.listTitle}>All Cards ({cards.length})</span>
          </div>
          <div style={styles.cardList}>
            {cards.map((card) => (
              <div
                key={card.id}
                style={{
                  ...styles.cardListItem,
                  ...(card.id === selectedCardId ? styles.cardListItemSelected : {}),
                }}
                onClick={() => setSelectedCardId(card.id === selectedCardId ? null : card.id)}
              >
                <div
                  style={{
                    ...styles.statusDot,
                    background: card.confirmed_name ? '#22c55e' : card.recognized_name ? '#f59e0b' : '#ef4444',
                  }}
                />
                <div style={styles.cardListName}>{card.display_name}</div>
                {card.match_score > 0 && (
                  <div style={styles.cardListScore}>{Math.round(card.match_score)}%</div>
                )}
              </div>
            ))}
            {cards.length === 0 && (
              <div style={styles.emptyList}>No cards detected yet</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Small helpers ─────────────────────────────────────────────────────────────

function StatChip({ color, label, pulse }: { color: string; label: string; pulse?: boolean }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '3px 10px',
        borderRadius: 20,
        background: `${color}1a`,
        border: `1px solid ${color}55`,
        fontSize: 12,
        color,
        animation: pulse ? 'pulse 1.2s ease-in-out infinite' : undefined,
      }}
    >
      <div style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
      {label}
    </div>
  );
}

function Spinner() {
  return (
    <div
      style={{
        width: 32,
        height: 32,
        border: '3px solid rgba(255,255,255,0.15)',
        borderTop: '3px solid #38bdf8',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }}
    />
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  root: {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    background: '#0f1117',
    color: '#e2e8f0',
    fontFamily: "'Segoe UI', system-ui, sans-serif",
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 20px',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
    flexShrink: 0,
  },
  title: {
    margin: 0,
    fontSize: 18,
    fontWeight: 700,
    letterSpacing: '0.02em',
    color: '#f8fafc',
  },
  headerActions: {
    display: 'flex',
    gap: 8,
    alignItems: 'center',
  },
  statsBar: {
    display: 'flex',
    gap: 8,
    padding: '8px 20px',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
    flexShrink: 0,
    flexWrap: 'wrap',
  },
  errorBanner: {
    background: 'rgba(239,68,68,0.12)',
    border: '1px solid rgba(239,68,68,0.3)',
    color: '#fca5a5',
    padding: '8px 16px',
    fontSize: 13,
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    flexShrink: 0,
  },
  dismissBtn: {
    background: 'none',
    border: 'none',
    color: '#fca5a5',
    fontSize: 18,
    cursor: 'pointer',
    lineHeight: 1,
  },
  body: {
    display: 'flex',
    flex: 1,
    overflow: 'hidden',
  },
  canvasWrap: {
    flex: 1,
    position: 'relative',
    overflow: 'hidden',
    background: '#080b10',
  },
  overlay: {
    position: 'absolute',
    inset: 0,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    background: 'rgba(8,11,16,0.7)',
    color: '#94a3b8',
    fontSize: 14,
    zIndex: 10,
  },
  emptyState: {
    position: 'absolute',
    inset: 0,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    cursor: 'pointer',
    color: '#475569',
  },
  emptyIcon: { fontSize: 48 },
  emptyText: { fontSize: 14, maxWidth: 200, textAlign: 'center', lineHeight: 1.5 },
  sidebar: {
    width: 280,
    borderLeft: '1px solid rgba(255,255,255,0.08)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    background: '#0c0f16',
    flexShrink: 0,
  },
  cardDetail: {
    padding: 14,
    borderBottom: '1px solid rgba(255,255,255,0.08)',
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  cardDetailHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  cardDetailTitle: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
    color: '#64748b',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#64748b',
    fontSize: 18,
    cursor: 'pointer',
    lineHeight: 1,
  },
  thumbnail: {
    width: '100%',
    borderRadius: 4,
    objectFit: 'cover',
    border: '1px solid rgba(255,255,255,0.08)',
  },
  fieldRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  },
  fieldLabel: {
    fontSize: 10,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    color: '#475569',
  },
  fieldValue: {
    fontSize: 13,
    color: '#cbd5e1',
    wordBreak: 'break-word',
  },
  editRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
  },
  editInput: {
    background: '#1e2738',
    border: '1px solid rgba(56,189,248,0.4)',
    borderRadius: 4,
    padding: '6px 10px',
    color: '#e2e8f0',
    fontSize: 13,
    outline: 'none',
  },
  cardActions: {
    display: 'flex',
    gap: 8,
    flexWrap: 'wrap',
  },
  listHeader: {
    padding: '10px 14px 6px',
    flexShrink: 0,
  },
  listTitle: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: 'uppercase',
    letterSpacing: '0.1em',
    color: '#64748b',
  },
  cardList: {
    flex: 1,
    overflowY: 'auto',
    padding: '0 8px 8px',
  },
  cardListItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '7px 8px',
    borderRadius: 5,
    cursor: 'pointer',
    transition: 'background 0.1s',
    marginBottom: 2,
  },
  cardListItemSelected: {
    background: 'rgba(56,189,248,0.12)',
    border: '1px solid rgba(56,189,248,0.25)',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    flexShrink: 0,
  },
  cardListName: {
    flex: 1,
    fontSize: 12,
    color: '#cbd5e1',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  cardListScore: {
    fontSize: 11,
    color: '#475569',
    flexShrink: 0,
  },
  emptyList: {
    padding: '16px 8px',
    fontSize: 12,
    color: '#475569',
    textAlign: 'center',
  },
  btn: {
    padding: '6px 12px',
    borderRadius: 5,
    fontSize: 12,
    fontWeight: 600,
    cursor: 'pointer',
    border: 'none',
    transition: 'opacity 0.1s',
  },
  btnPrimary: {
    background: '#1d4ed8',
    color: '#fff',
    border: '1px solid #2563eb',
  },
  btnOutline: {
    background: 'transparent',
    color: '#94a3b8',
    border: '1px solid rgba(255,255,255,0.15)',
  },
  btnActive: {
    background: 'rgba(56,189,248,0.2)',
    color: '#38bdf8',
    border: '1px solid rgba(56,189,248,0.5)',
  },
};