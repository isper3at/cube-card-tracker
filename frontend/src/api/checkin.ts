import { apiFetch, apiUpload, API_URL } from './client';
import { Card, Cube } from '../types';

export interface StartCheckinPayload {
  tournament_id: number;
  owner_name: string;
  owner_email?: string;
  cube_name: string;
}

export interface StartCheckinResponse {
  session_id: string;
  cube: Cube;
}

export interface UploadResponse {
  message: string;
}

export function startCheckin(payload: StartCheckinPayload): Promise<StartCheckinResponse> {
  return apiFetch('/api/checkin/start', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getSession(sessionId: string): Promise<Cube> {
  return apiFetch(`/api/checkin/${sessionId}`);
}

export function uploadImage(sessionId: string, file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('image', file);
  return apiUpload(`/api/checkin/${sessionId}/upload`, formData);
}

export function listCards(sessionId: string): Promise<Card[]> {
  return apiFetch(`/api/checkin/${sessionId}/cards`);
}

export function updateCard(sessionId: string, cardId: number, confirmedName: string): Promise<Card> {
  return apiFetch(`/api/checkin/${sessionId}/cards/${cardId}`, {
    method: 'PATCH',
    body: JSON.stringify({ confirmed_name: confirmedName }),
  });
}

export function finalizeCheckin(sessionId: string): Promise<Cube> {
  return apiFetch(`/api/checkin/${sessionId}/finalize`, { method: 'POST' });
}

// Returns a URL the browser can use directly in an <img> src
export function getAnnotatedImageUrl(sessionId: string): string {
  return `${API_URL}/api/checkin/${sessionId}/annotated`;
}

