/**
 * CardList.tsx
 *
 * Sidebar showing detected cards with inline edit support.
 */

import React, { useState } from "react";
import type { CanvasCard } from "./CardCanvas";

interface Props {
  cards: CanvasCard[];
  highlightId: string | null;
  thumbnails: Record<string, string>;
  onRemoveCard: (id: string) => void;
  onHighlight: (id: string | null) => void;
  onSaveEdit?: (id: string, newName: string) => void;
  startEditId?: string | null;
}

type Tab = "found" | "unknown";

const COLORS = {
  confirmed: "#22d3ee",
  matched: "#4ade80",
  weak: "#facc15",
  unknown: "#f87171",
} as const;

function dotColor(c: CanvasCard): string {
  if (c.confirmed_name) return COLORS.confirmed;
  if (c.recognized_name && c.match_score >= 0.75) return COLORS.matched;
  if (c.recognized_name) return COLORS.weak;
  return COLORS.unknown;
}

export default function CardList({
  cards,
  highlightId,
  thumbnails,
  onRemoveCard,
  onHighlight,
  onSaveEdit,
  startEditId,
}: Props) {
  const [tab, setTab] = useState<Tab>("found");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>("");

  // respond to external requests to start editing (e.g. double-click on canvas)
  React.useEffect(() => {
    if (!startEditId) return;
    const card = cards.find((c) => c.id === startEditId);
    if (!card) return;
    setEditingId(card.id);
    setEditValue(
      card.confirmed_name ?? card.recognized_name ?? card.raw_ocr_text ?? ""
    );
  }, [startEditId, cards]);

  const found = cards.filter((c) => c.recognized_name || c.confirmed_name);
  const unknown = cards.filter((c) => !c.recognized_name && !c.confirmed_name);
  const list = tab === "found" ? found : unknown;

  function startEdit(card: CanvasCard) {
    setEditingId(card.id);
    setEditValue(
      card.confirmed_name ?? card.recognized_name ?? card.raw_ocr_text ?? ""
    );
  }

  function finishEdit(id: string) {
    setEditingId(null);
    const trimmed = editValue.trim();
    if (trimmed) {
      onSaveEdit?.(id, trimmed);
    }
  }

  function cancelEdit() {
    setEditingId(null);
  }

  return (
    <aside style={S.root}>
      <div style={S.tabBar}>
        <TabButton
          active={tab === "found"}
          count={found.length}
          accentColor={COLORS.matched}
          onClick={() => setTab("found")}
        >
          Found
        </TabButton>
        <TabButton
          active={tab === "unknown"}
          count={unknown.length}
          accentColor={COLORS.unknown}
          onClick={() => setTab("unknown")}
        >
          Unknown
        </TabButton>
      </div>

      <div style={S.list}>
        {list.length === 0 ? (
          <EmptyState tab={tab} />
        ) : (
          list.map((card) => (
            <div key={card.id} style={{ padding: 6 }}>
              <CardRow
                card={card}
                thumbnail={thumbnails[card.id] ?? null}
                isHighlighted={card.id === highlightId}
                onRemove={() => onRemoveCard(card.id)}
                onEnter={() => onHighlight(card.id)}
                onLeave={() => onHighlight(null)}
                onStartEdit={() => startEdit(card)}
                isEditing={editingId === card.id}
                editValue={editingId === card.id ? editValue : undefined}
                onChangeEdit={(v) => setEditValue(v)}
                onSave={() => finishEdit(card.id)}
                onCancel={() => cancelEdit()}
              />
            </div>
          ))
        )}
      </div>

      <footer style={S.footer}>
        <Stat label="Total" value={cards.length} color="#334155" />
        <div style={S.footDiv} />
        <Stat label="Found" value={found.length} color={COLORS.matched} />
        <div style={S.footDiv} />
        <Stat label="Unknown" value={unknown.length} color={COLORS.unknown} />
      </footer>
    </aside>
  );
}

function TabButton({
  children,
  active,
  count,
  accentColor,
  onClick,
}: {
  children: React.ReactNode;
  active: boolean;
  count: number;
  accentColor: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        ...S.tab,
        borderBottom: active
          ? `2px solid ${accentColor}`
          : "2px solid transparent",
      }}
    >
      <span style={{ color: active ? "#e2e8f0" : "#334155" }}>
        {children}
      </span>
      <span
        style={{
          ...S.badge,
          background: active
            ? accentColor
            : "rgba(255,255,255,0.05)",
          color:
            active && accentColor === "#facc15"
              ? "#1a1208"
              : active
                ? "#050a14"
                : "#334155",
        }}
      >
        {count}
      </span>
    </button>
  );
}

function CardRow({
  card,
  thumbnail,
  isHighlighted,
  onRemove,
  onEnter,
  onLeave,
  onStartEdit,
  isEditing,
  editValue,
  onChangeEdit,
  onSave,
  onCancel,
}: {
  card: CanvasCard;
  thumbnail: string | null;
  isHighlighted: boolean;
  onRemove: () => void;
  onEnter: () => void;
  onLeave: () => void;
  onStartEdit: () => void;
  isEditing?: boolean;
  editValue?: string;
  onChangeEdit?: (v: string) => void;
  onSave?: () => void;
  onCancel?: () => void;
}) {
  const [hov, setHov] = useState(false);
  const name =
    card.confirmed_name ??
    card.recognized_name ??
    card.raw_ocr_text ??
    "UNKNOWN CARD";
  const score =
    card.recognized_name && card.match_score > 0
      ? Math.round(card.match_score * 100)
      : null;

  return (
    <div
      style={{
        ...S.row,
        background: isHighlighted
          ? "rgba(99,102,241,0.10)"
          : hov
            ? "rgba(255,255,255,0.025)"
            : "transparent",
        outline: isHighlighted
          ? "1px solid rgba(99,102,241,0.25)"
          : "none",
      }}
      onMouseEnter={() => {
        setHov(true);
        onEnter();
      }}
      onMouseLeave={() => {
        setHov(false);
        onLeave();
      }}
    >
      <span style={{ ...S.dot, background: dotColor(card) }} />

      {thumbnail ? (
        <img
          src={`data:image/jpeg;base64,${thumbnail}`}
          alt=""
          style={S.thumb}
        />
      ) : (
        <div style={S.thumbBlank} />
      )}

      <div style={S.nameWrap} onDoubleClick={() => onStartEdit()}>
        {isEditing ? (
          <div style={S.editContainer}>
            <input
              autoFocus
              value={editValue ?? ""}
              onChange={(e) => onChangeEdit?.(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  onSave?.();
                }
                if (e.key === "Escape") {
                  e.preventDefault();
                  onCancel?.();
                }
              }}
              style={S.editInput}
              placeholder="Card name..."
            />
            <div style={S.editButtons}>
              <button
                title="Save (Enter)"
                onClick={(e) => {
                  e.stopPropagation();
                  onSave?.();
                }}
                style={S.btnSave}
                disabled={!(editValue?.trim())}
              >
                ✓
              </button>
              <button
                title="Cancel (Esc)"
                onClick={(e) => {
                  e.stopPropagation();
                  onCancel?.();
                }}
                style={S.btnCancel}
              >
                ✕
              </button>
            </div>
          </div>
        ) : (
          <>
            <span style={S.name} title={name}>
              {name}
            </span>
            {score !== null && <span style={S.score}>{score}%</span>}
          </>
        )}
      </div>

      <button
        title="Remove detection"
        onClick={(e) => {
          e.stopPropagation();
          onRemove();
        }}
        style={{ ...S.xBtn, color: hov ? "#f87171" : "#1e293b" }}
      >
        ×
      </button>
    </div>
  );
}

function EmptyState({ tab }: { tab: Tab }) {
  return (
    <div style={S.empty}>
      <span style={S.emptyGlyph}>
        {tab === "found" ? "◈" : "◎"}
      </span>
      <span>
        {tab === "found"
          ? "No cards matched yet."
          : "No unknown regions."}
      </span>
      {tab === "found" && (
        <span style={{ color: "#1e293b", fontSize: 10 }}>
          Draw a box on the image to detect a card.
        </span>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div style={S.stat}>
      <span style={{ fontSize: 15, fontWeight: 700, color }}>
        {value}
      </span>
      <span
        style={{
          fontSize: 9,
          color: "#1e293b",
          letterSpacing: "0.08em",
          textTransform: "uppercase" as const,
        }}
      >
        {label}
      </span>
    </div>
  );
}

const S: Record<string, React.CSSProperties> = {
  root: {
    width: 268,
    flexShrink: 0,
    display: "flex",
    flexDirection: "column",
    background: "#07101e",
    borderLeft: "1px solid rgba(255,255,255,0.05)",
    fontFamily: '"DM Mono","Fira Code",monospace',
    overflow: "hidden",
  },
  tabBar: {
    display: "flex",
    borderBottom: "1px solid rgba(255,255,255,0.05)",
    padding: "6px 6px 0",
    gap: 4,
    flexShrink: 0,
  },
  tab: {
    flex: 1,
    background: "none",
    border: "none",
    borderRadius: "5px 5px 0 0",
    padding: "7px 6px 9px",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    fontSize: 11,
    fontFamily: "inherit",
    letterSpacing: "0.05em",
    transition: "all 0.15s",
  },
  badge: {
    borderRadius: 10,
    fontSize: 10,
    fontWeight: 700,
    padding: "1px 6px",
    minWidth: 18,
    textAlign: "center" as const,
    transition: "all 0.2s",
  },
  list: {
    flex: 1,
    overflowY: "auto" as const,
    padding: "4px 0",
    scrollbarWidth: "thin" as const,
    scrollbarColor: "#1e293b transparent",
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: 7,
    padding: "5px 10px 5px 10px",
    borderRadius: 6,
    margin: "1px 4px",
    cursor: "default",
    transition: "background 0.1s, outline 0.1s",
  },
  dot: { width: 6, height: 6, borderRadius: "50%", flexShrink: 0 },
  thumb: {
    width: 40,
    height: 24,
    objectFit: "cover" as const,
    borderRadius: 3,
    border: "1px solid rgba(255,255,255,0.07)",
    flexShrink: 0,
    background: "#0d1727",
  },
  thumbBlank: {
    width: 40,
    height: 24,
    borderRadius: 3,
    background: "rgba(255,255,255,0.03)",
    border: "1px dashed rgba(255,255,255,0.06)",
    flexShrink: 0,
  },
  nameWrap: {
    flex: 1,
    display: "flex",
    alignItems: "baseline",
    gap: 5,
    minWidth: 0,
  },
  editContainer: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    width: "100%",
    minWidth: 0,
  },
  editInput: {
    flex: 1,
    minWidth: 0,
    padding: "6px 8px",
    borderRadius: 6,
    border: "1px solid rgba(76, 175, 80, 0.4)",
    background: "#07101e",
    color: "#e2e8f0",
    fontFamily: '"DM Mono","Fira Code",monospace',
    fontSize: 11,
  },
  editButtons: {
    display: "flex",
    gap: 3,
    flexShrink: 0,
  },
  btnSave: {
    background: "#4ade80",
    border: "none",
    borderRadius: 4,
    padding: "4px 7px",
    color: "#050a14",
    fontSize: 12,
    fontWeight: 700,
    cursor: "pointer",
    transition: "opacity 0.1s, background 0.1s",
  } as React.CSSProperties,
  btnCancel: {
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 4,
    padding: "4px 7px",
    color: "#f87171",
    fontSize: 12,
    fontWeight: 700,
    cursor: "pointer",
    transition: "opacity 0.1s, background 0.1s",
  } as React.CSSProperties,
  name: {
    fontSize: 11,
    color: "#64748b",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
    flex: 1,
  },
  score: {
    fontSize: 9,
    color: "#166534",
    background: "#052e16",
    padding: "1px 5px",
    borderRadius: 3,
    flexShrink: 0,
  },
  xBtn: {
    background: "none",
    border: "none",
    fontSize: 18,
    lineHeight: 1,
    cursor: "pointer",
    padding: "0 2px",
    flexShrink: 0,
    fontFamily: "monospace",
    transition: "color 0.12s",
  },
  empty: {
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    gap: 5,
    padding: "36px 20px",
    fontSize: 11,
    color: "#1e3a5f",
    textAlign: "center" as const,
  },
  emptyGlyph: {
    fontSize: 26,
    color: "#0d1727",
    marginBottom: 4,
  },
  footer: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-around",
    padding: "9px 12px",
    borderTop: "1px solid rgba(255,255,255,0.05)",
    flexShrink: 0,
  },
  footDiv: { width: 1, height: 20, background: "rgba(255,255,255,0.06)" },
  stat: {
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    gap: 2,
  },
};
