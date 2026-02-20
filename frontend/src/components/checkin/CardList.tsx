import { useState } from 'react';
import { updateCard } from '../../api/checkin';
import { Card } from '../../types';

interface Props {
  cards: Card[];
  sessionId: string;
  onCardUpdated: (card: Card) => void;
}

export function CardList({ cards, sessionId, onCardUpdated }: Props) {
  // Which card is currently being edited, and the draft value
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState('');
  const [savingId, setSavingId] = useState<number | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  function startEdit(card: Card) {
    setEditingId(card.id);
    setEditValue(card.confirmed_name ?? card.recognized_name ?? '');
    setSaveError(null);
  }

  function cancelEdit() {
    setEditingId(null);
    setSaveError(null);
  }

  async function saveEdit(card: Card) {
    const name = editValue.trim();
    if (!name) return;

    setSavingId(card.id);
    setSaveError(null);
    try {
      const updated = await updateCard(sessionId, card.id, name);
      onCardUpdated(updated);
      setEditingId(null);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSavingId(null);
    }
  }

  if (cards.length === 0) {
    return (
      <p className="text-center py-10 text-gray-400">
        No cards detected yet. Upload an image to begin.
      </p>
    );
  }

  const identified = cards.filter((c) => c.confirmed_name ?? c.recognized_name).length;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <span className="font-medium text-gray-700">
          {cards.length} card{cards.length !== 1 ? 's' : ''} detected
        </span>
        <span className="text-sm text-gray-500">{identified} identified</span>
      </div>

      {saveError && (
        <p className="mb-2 text-sm text-red-600">{saveError}</p>
      )}

      <ul className="space-y-2">
        {cards.map((card) => {
          const isEditing = editingId === card.id;
          const isSaving = savingId === card.id;

          // Pick row colour based on match status
          const rowClass = card.confirmed_name
            ? 'bg-green-50 border-green-200'
            : card.recognized_name
            ? 'bg-amber-50 border-amber-200'
            : 'bg-red-50 border-red-200';

          // Status badge
          const badge = card.confirmed_name
            ? { label: 'Confirmed', cls: 'bg-green-500 text-white' }
            : card.recognized_name
            ? { label: `${Math.round((card.match_score ?? 0) * 100)}%`, cls: 'bg-amber-400 text-white' }
            : { label: 'Unknown', cls: 'bg-red-500 text-white' };

          return (
            <li
              key={card.id}
              className={`flex items-center gap-3 border rounded-lg p-3 ${rowClass}`}
            >
              {/* Thumbnail */}
              {card.thumbnail_base64 ? (
                <img
                  src={`data:image/jpeg;base64,${card.thumbnail_base64}`}
                  alt=""
                  className="w-10 h-14 object-cover rounded flex-shrink-0"
                />
              ) : (
                <div className="w-10 h-14 rounded bg-gray-200 flex items-center justify-center text-gray-400 text-xs flex-shrink-0">
                  ?
                </div>
              )}

              {/* Name / edit field */}
              <div className="flex-1 min-w-0">
                {isEditing ? (
                  <input
                    autoFocus
                    className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveEdit(card);
                      if (e.key === 'Escape') cancelEdit();
                    }}
                  />
                ) : (
                  <p className="text-sm font-medium truncate">{card.display_name}</p>
                )}
                {card.raw_ocr_text && !isEditing && (
                  <p className="text-xs text-gray-400 truncate">OCR: {card.raw_ocr_text}</p>
                )}
              </div>

              {/* Badge */}
              <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${badge.cls}`}>
                {badge.label}
              </span>

              {/* Actions */}
              {isEditing ? (
                <div className="flex gap-1 flex-shrink-0">
                  <button
                    onClick={() => saveEdit(card)}
                    disabled={isSaving}
                    className="text-xs bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700 disabled:opacity-50"
                  >
                    {isSaving ? '…' : 'Save'}
                  </button>
                  <button
                    onClick={cancelEdit}
                    className="text-xs bg-gray-200 px-2 py-1 rounded hover:bg-gray-300"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => startEdit(card)}
                  className="text-xs text-blue-600 hover:underline flex-shrink-0"
                >
                  Edit
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

