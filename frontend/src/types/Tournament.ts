import { Cube } from './Cube';

export type TournamentStatus = 'draft' | 'active' | 'complete' | 'cancelled';

export interface Tournament {
  id: number;
  name: string;
  date: string;
  location: string | null;
  status: TournamentStatus;
  notes: string | null;
  cubes?: Cube[];
  created_at: string;
  updated_at: string;
}

