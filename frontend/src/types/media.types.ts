/** Media attachment returned by the API. */
export interface MediaAttachment {
  id: string;
  user_id: string;
  trade_id: string;
  object_key: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  /** 'image' or 'video'. */
  media_type: 'image' | 'video';
  created_at: string;
}
