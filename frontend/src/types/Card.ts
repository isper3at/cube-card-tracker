export interface Card {
  id: number;
  cube_id: number;
  raw_ocr_text: string | null;
  recognized_name: string | null;
  confirmed_name: string | null;
  match_score: number | null;
  status: 'detected' | 'confirmed' | 'drafted' | 'returned';
  display_name: string;
  bbox_x: number;
  bbox_y: number;
  bbox_width: number;
  bbox_height: number;
  polygon_json: number[][];
  thumbnail_base64: string | null;
  created_at: string;
  updated_at: string;
}

