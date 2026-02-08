import apiClient from './client';
import type { Tag } from '../types/marketData.types';

/** List all tags for the current user. */
export async function listTags(): Promise<Tag[]> {
  const res = await apiClient.get<{ tags: Tag[] }>('/tags');
  return res.data.tags;
}

/** Create a new tag. */
export async function createTag(
  name: string,
  color: string
): Promise<Tag> {
  const res = await apiClient.post<{ tag: Tag }>('/tags', {
    name,
    color,
  });
  return res.data.tag;
}

/** Update a tag. */
export async function updateTag(
  id: string,
  name: string,
  color: string
): Promise<Tag> {
  const res = await apiClient.put<{ tag: Tag }>(`/tags/${id}`, {
    name,
    color,
  });
  return res.data.tag;
}

/** Delete a tag. */
export async function deleteTag(id: string): Promise<void> {
  await apiClient.delete(`/tags/${id}`);
}
