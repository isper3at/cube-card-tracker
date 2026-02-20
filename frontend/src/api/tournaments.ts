import { apiFetch } from './client';
import { Tournament } from '../types';

export function listTournaments(): Promise<Tournament[]> {
  return apiFetch('/api/tournaments/');
}

export function createTournament(name: string, date: string, location?: string): Promise<Tournament> {
  return apiFetch('/api/tournaments/', {
    method: 'POST',
    body: JSON.stringify({ name, date, location }),
  });
}

export function getTournament(id: number): Promise<Tournament> {
  return apiFetch(`/api/tournaments/${id}`);
}

