import apiClient from './client';
import type { MediaAttachment } from '../types/media.types';

/** Upload a media file for a trade. */
export async function uploadMedia(
  tradeId: string,
  file: File
): Promise<MediaAttachment> {
  const form = new FormData();
  form.append('file', file);

  const res = await apiClient.post<{ media: MediaAttachment }>(
    `/trades/${tradeId}/media`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  );
  return res.data.media;
}

/** List all media attachments for a trade. */
export async function listMedia(
  tradeId: string
): Promise<MediaAttachment[]> {
  const res = await apiClient.get<{ media: MediaAttachment[] }>(
    `/trades/${tradeId}/media`
  );
  return res.data.media;
}

/** Get a presigned URL for a media attachment. */
export async function getMediaUrl(
  mediaId: string
): Promise<string> {
  const res = await apiClient.get<{ url: string }>(
    `/media/${mediaId}/url`
  );
  return res.data.url;
}

/** Delete a media attachment. */
export async function deleteMedia(
  mediaId: string
): Promise<void> {
  await apiClient.delete(`/media/${mediaId}`);
}
