import { Card } from './Card';

export type CubeStatus =
  | 'pending_checkin'
  | 'checked_in'
  | 'in_use'
  | 'returned'
  | 'flagged';

export interface Cube {
  id: number;
  tournament_id: number;
  owner_name: string;
  owner_email: string | null;
  cube_name: string;
  status: CubeStatus;
  session_id: string | null;
  total_cards: number;
  cards_confirmed: number;
  annotated_image_path: string | null;
  cards?: Card[];
  created_at: string;
  updated_at: string;
}

