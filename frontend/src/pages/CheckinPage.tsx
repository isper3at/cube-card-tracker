import { useState, useEffect, FormEvent } from 'react';
import { listTournaments, createTournament } from '../api/tournaments';
import { startCheckin, uploadImage } from '../api/checkin';
import CheckinFlow from '../components/checkin/CheckinFlow';
import { ImageUpload } from '../components/checkin/ImageUpload';
import { Tournament, Cube } from '../types';

type View = 'select-tournament' | 'upload-image' | 'checkin';
type CheckinState = { cubeId: number; imageUrl: string; sessionId: string } | null;

export function CheckinPage() {
  const [view, setView] = useState<View>('select-tournament');
  const [tournaments, setTournaments] = useState<Tournament[]>([]);
  const [activeTournament, setActiveTournament] = useState<Tournament | null>(null);
  const [checkinState, setCheckinState] = useState<CheckinState>(null);
  const [checkedInCubes, setCheckedInCubes] = useState<Cube[]>([]);

  // Create-tournament form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDate, setNewDate] = useState(new Date().toISOString().slice(0, 10));
  const [newLocation, setNewLocation] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [checkinError, setCheckinError] = useState<string | null>(null);
  const [isUploadingImage, setIsUploadingImage] = useState(false);

  // Load existing tournaments on mount
  useEffect(() => {
    listTournaments()
      .then(setTournaments)
      .catch((err: unknown) =>
        setLoadError(err instanceof Error ? err.message : 'Failed to load tournaments')
      );
  }, []);

  async function handleCreateTournament(e: FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCreating(true);
    try {
      const created = await createTournament(newName.trim(), newDate, newLocation.trim() || undefined);
      setTournaments((prev) => [created, ...prev]);
      setActiveTournament(created);
      setShowCreateForm(false);
      setNewName('');
      setNewLocation('');
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create tournament');
    } finally {
      setCreating(false);
    }
  }

  function handleSelectTournament(t: Tournament) {
    setActiveTournament(t);
    setView('upload-image');
  }

  async function handleImageSelected(file: File) {
    setCheckinError(null);
    setIsUploadingImage(true);

    try {
      // Start a new checkin session
      const checkinResponse = await startCheckin({
        tournament_id: activeTournament!.id,
        owner_name: activeTournament!.name,
        cube_name: `${activeTournament!.name} - ${new Date().toLocaleDateString()}`,
      });

      const sessionId = checkinResponse.session_id;

      // Upload the image
      await uploadImage(sessionId, file);

      const imageUrl = URL.createObjectURL(file);
      setCheckinState({ cubeId: checkinResponse.cube.id, imageUrl, sessionId });
      setView('checkin');
    } catch (err) {
      setCheckinError(err instanceof Error ? err.message : 'Failed to start checkin');
    } finally {
      setIsUploadingImage(false);
    }
  }

  function handleCheckinComplete(cube: Cube) {
    setCheckedInCubes((prev) => [cube, ...prev]);
    // Reset to upload view for next cube
    setCheckinState(null);
    setView('upload-image');
  }

  // ── Tournament selection screen ───────────────────────────
  if (view === 'select-tournament') {
    return (
      <div className="min-h-screen bg-gray-50">
        <header className="bg-white border-b px-6 py-4">
          <h1 className="text-lg font-bold text-gray-800">🎴 Cube Card Tracker</h1>
        </header>

        <main className="max-w-lg mx-auto p-6">
          <h2 className="text-xl font-semibold text-gray-800 mb-1">Select a tournament</h2>
          <p className="text-sm text-gray-500 mb-6">
            Choose an existing tournament or create a new one to begin checking in cubes.
          </p>

          {loadError && (
            <p className="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
              {loadError}
            </p>
          )}

          {/* Existing tournaments */}
          {tournaments.length > 0 && (
            <ul className="space-y-2 mb-6">
              {tournaments.map((t) => (
                <li key={t.id}>
                  <button
                    onClick={() => handleSelectTournament(t)}
                    className="w-full text-left bg-white border border-gray-200 rounded-xl p-4 hover:border-blue-400 hover:bg-blue-50 transition-colors"
                  >
                    <p className="font-medium text-gray-800">{t.name}</p>
                    <p className="text-sm text-gray-500">
                      {t.date}{t.location ? ` · ${t.location}` : ''}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {/* Create new tournament */}
          {showCreateForm ? (
            <div className="bg-white border border-gray-200 rounded-xl p-5">
              <h3 className="font-medium text-gray-800 mb-4">New tournament</h3>
              {createError && (
                <p className="mb-3 text-sm text-red-600">{createError}</p>
              )}
              <form onSubmit={handleCreateTournament} className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Name <span className="text-red-500">*</span>
                  </label>
                  <input
                    required
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="Friday Night Cube"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Date <span className="text-red-500">*</span>
                  </label>
                  <input
                    required
                    type="date"
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={newDate}
                    onChange={(e) => setNewDate(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Location</label>
                  <input
                    className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={newLocation}
                    onChange={(e) => setNewLocation(e.target.value)}
                    placeholder="Game store, city…"
                  />
                </div>
                <div className="flex gap-2 pt-1">
                  <button
                    type="submit"
                    disabled={creating}
                    className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                  >
                    {creating ? 'Creating…' : 'Create'}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setShowCreateForm(false); setCreateError(null); }}
                    className="flex-1 bg-gray-100 text-gray-700 py-2 rounded-lg text-sm font-medium hover:bg-gray-200"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          ) : (
            <button
              onClick={() => setShowCreateForm(true)}
              className="w-full border-2 border-dashed border-gray-300 rounded-xl p-4 text-gray-500 hover:border-blue-400 hover:text-blue-600 transition-colors text-sm font-medium"
            >
              + Create new tournament
            </button>
          )}
        </main>
      </div>
    );
  }

  // ── Check-in screen ───────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-3 flex items-center gap-3">
        <button
          onClick={() => { setView('select-tournament'); setCheckedInCubes([]); setCheckinState(null); }}
          className="text-gray-400 hover:text-gray-700 text-sm"
        >
          ← Tournaments
        </button>
        <span className="text-gray-300">|</span>
        <div>
          <span className="font-semibold text-gray-800">{activeTournament?.name}</span>
          {activeTournament?.location && (
            <span className="text-sm text-gray-400 ml-2">{activeTournament.location}</span>
          )}
        </div>
        {checkedInCubes.length > 0 && (
          <span className="ml-auto text-sm text-gray-500">
            {checkedInCubes.length} cube{checkedInCubes.length !== 1 ? 's' : ''} checked in
          </span>
        )}
      </header>

      {/* Completed cubes summary strip */}
      {checkedInCubes.length > 0 && (
        <div className="bg-green-50 border-b border-green-200 px-6 py-2 flex items-center gap-4 overflow-x-auto">
          {checkedInCubes.map((cube) => (
            <span key={cube.id} className="text-sm text-green-700 whitespace-nowrap">
              ✓ {cube.cube_name} ({cube.total_cards} cards)
            </span>
          ))}
        </div>
      )}

      {/* Upload image or show checkin flow */}
      {view === 'upload-image' && (
        <main className="max-w-2xl mx-auto p-6">
          <h2 className="text-xl font-semibold text-gray-800 mb-1">Upload cube image</h2>
          <p className="text-sm text-gray-500 mb-6">
            Take a photo of your cube or upload an existing image to begin detection.
          </p>
          {checkinError && (
            <p className="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
              {checkinError}
            </p>
          )}
          <ImageUpload onFileSelected={handleImageSelected} disabled={isUploadingImage} />
        </main>
      )}

      {view === 'checkin' && checkinState && (
        <CheckinFlow
          cubeId={checkinState.cubeId}
          imageUrl={checkinState.imageUrl}
          sessionId={checkinState.sessionId}
          onFinalize={(cards) => {
            // TODO: Save cards to backend, then call handleCheckinComplete with the cube
            const cube: Cube = {
              id: checkinState.cubeId,
              tournament_id: activeTournament?.id || 0,
              owner_name: 'Unknown',
              owner_email: null,
              cube_name: `Cube ${checkinState.cubeId}`,
              status: 'checked_in',
              session_id: checkinState.sessionId,
              total_cards: cards.length,
              cards_confirmed: 0,
              annotated_image_path: null,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            };
            handleCheckinComplete(cube);
          }}
        />
      )}
    </div>
  );
}