import { useState, FormEvent } from 'react';
import { startCheckin, uploadImage, finalizeCheckin, getAnnotatedImageUrl } from '../../api/checkin';
import { Card, Cube } from '../../types';
import { CardCanvas } from './CardCanvas';
import { CardList } from './CardList';
import { ImageUpload } from './ImageUpload';

type Step = 'details' | 'upload' | 'review' | 'done';

const STEPS: Step[] = ['details', 'upload', 'review', 'done'];
const STEP_LABELS: Record<Step, string> = {
  details: 'Details',
  upload: 'Upload',
  review: 'Review',
  done: 'Done',
};

interface Props {
  tournamentId: number;
  onComplete?: (cube: Cube) => void;
}

export function CheckinFlow({ tournamentId, onComplete }: Props) {
  const [step, setStep] = useState<Step>('details');

  // Session state
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [cube, setCube] = useState<Cube | null>(null);
  const [cards, setCards] = useState<Card[]>([]);
  const [annotatedUrl, setAnnotatedUrl] = useState<string | null>(null);

  // UI state
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form fields
  const [ownerName, setOwnerName] = useState('');
  const [ownerEmail, setOwnerEmail] = useState('');
  const [cubeName, setCubeName] = useState('');

  // ── Step 1: submit owner/cube details ─────────────────────
  async function handleDetailsSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await startCheckin({
        tournament_id: tournamentId,
        owner_name: ownerName.trim(),
        owner_email: ownerEmail.trim() || undefined,
        cube_name: cubeName.trim(),
      });
      setSessionId(res.session_id);
      setCube(res.cube);
      setStep('upload');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start check-in');
    } finally {
      setBusy(false);
    }
  }

  // ── Step 2: upload photo + process ────────────────────────
  async function handleImageSelected(file: File) {
    if (!sessionId) return;
    setError(null);
    setBusy(true);
    try {
      const res = await uploadImage(sessionId, file);
      setCards(res.cards);
      // Cache-bust so the browser re-fetches the newly created annotated image
      setAnnotatedUrl(`${getAnnotatedImageUrl(sessionId)}?t=${Date.now()}`);
      setStep('review');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Image processing failed');
    } finally {
      setBusy(false);
    }
  }

  // ── Step 3: finalize ──────────────────────────────────────
  async function handleFinalize() {
    if (!sessionId) return;
    setError(null);
    setBusy(true);
    try {
      const finalized = await finalizeCheckin(sessionId);
      setCube(finalized);
      setStep('done');
      onComplete?.(finalized);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Finalize failed');
    } finally {
      setBusy(false);
    }
  }

  function handleCardUpdated(updated: Card) {
    setCards((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  }

  const identified = cards.filter((c) => c.confirmed_name ?? c.recognized_name).length;
  const currentStepIndex = STEPS.indexOf(step);

  return (
    <div className="max-w-3xl mx-auto p-6">

      {/* Progress bar */}
      <div className="flex items-center gap-2 mb-8">
        {STEPS.map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={[
              'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold',
              i < currentStepIndex ? 'bg-green-500 text-white' :
              i === currentStepIndex ? 'bg-blue-600 text-white' :
              'bg-gray-200 text-gray-400',
            ].join(' ')}>
              {i < currentStepIndex ? '✓' : i + 1}
            </div>
            <span className={`text-sm hidden sm:block ${i === currentStepIndex ? 'text-gray-800 font-medium' : 'text-gray-400'}`}>
              {STEP_LABELS[s]}
            </span>
            {i < STEPS.length - 1 && (
              <div className={`h-0.5 w-6 ${i < currentStepIndex ? 'bg-green-400' : 'bg-gray-200'}`} />
            )}
          </div>
        ))}
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {/* ── Step 1: Details ── */}
      {step === 'details' && (
        <div className="bg-white border rounded-xl p-6 shadow-sm">
          <h2 className="text-xl font-semibold mb-5">Cube details</h2>
          <form onSubmit={handleDetailsSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Owner name <span className="text-red-500">*</span>
              </label>
              <input
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
                placeholder="Alice"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Owner email
              </label>
              <input
                type="email"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={ownerEmail}
                onChange={(e) => setOwnerEmail(e.target.value)}
                placeholder="alice@example.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Cube name <span className="text-red-500">*</span>
              </label>
              <input
                required
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={cubeName}
                onChange={(e) => setCubeName(e.target.value)}
                placeholder="Alice's Powered Cube"
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="w-full bg-blue-600 text-white py-2.5 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {busy ? 'Starting…' : 'Next →'}
            </button>
          </form>
        </div>
      )}

      {/* ── Step 2: Upload ── */}
      {step === 'upload' && (
        <div className="bg-white border rounded-xl p-6 shadow-sm">
          <h2 className="text-xl font-semibold mb-1">Upload a photo</h2>
          <p className="text-gray-500 text-sm mb-6">
            Lay all cards face-up and take one photo. The system will detect and OCR each card name.
          </p>
          {busy ? (
            <div className="text-center py-16">
              <div className="text-4xl animate-spin mb-4">⚙️</div>
              <p className="text-gray-600">Detecting cards…</p>
            </div>
          ) : (
            <ImageUpload onFileSelected={handleImageSelected} />
          )}
        </div>
      )}

      {/* ── Step 3: Review ── */}
      {step === 'review' && (
        <div className="bg-white border rounded-xl p-6 shadow-sm">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h2 className="text-xl font-semibold">Review cards</h2>
              <p className="text-sm text-gray-500 mt-0.5">
                {identified}/{cards.length} identified · click Edit to correct any name
              </p>
            </div>
            <button
              onClick={handleFinalize}
              disabled={busy}
              className="bg-green-600 text-white px-5 py-2 rounded-lg font-medium hover:bg-green-700 disabled:opacity-50 flex-shrink-0"
            >
              {busy ? 'Saving…' : 'Finalise ✓'}
            </button>
          </div>

          {annotatedUrl && (
            <div className="mb-5">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Annotated scan</p>
              <CardCanvas imageUrl={annotatedUrl} />
            </div>
          )}

          <CardList cards={cards} sessionId={sessionId!} onCardUpdated={handleCardUpdated} />
        </div>
      )}

      {/* ── Step 4: Done ── */}
      {step === 'done' && cube && (
        <div className="bg-white border rounded-xl p-10 shadow-sm text-center">
          <div className="text-5xl mb-4">✅</div>
          <h2 className="text-2xl font-bold text-green-700 mb-2">Check-in complete</h2>
          <p className="text-gray-700 mb-1">
            <strong>{cube.cube_name}</strong> — {cube.owner_name}
          </p>
          <p className="text-gray-500 text-sm">
            {cube.total_cards} cards · {cube.cards_confirmed} confirmed
          </p>
        </div>
      )}
    </div>
  );
}

