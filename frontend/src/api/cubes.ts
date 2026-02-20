import { apiFetch } from './client';
import { Cube, Card } from '../types';

export function listCubes(tournamentId?: number): Promise<Cube[]> {
  const qs = tournamentId ? `?tournament_id=${tournamentId}` : '';
  return apiFetch(`/api/cubes/${qs}`);
}

export function getCube(cubeId: number): Promise<Cube> {
  return apiFetch(`/api/cubes/${cubeId}`);
}

export function getCubeCards(cubeId: number): Promise<Card[]> {
  return apiFetch(`/api/cubes/${cubeId}/cards`);
}

