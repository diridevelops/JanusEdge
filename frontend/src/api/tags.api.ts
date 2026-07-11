import apiClient from './client';
import type { Tag, TagCategory } from '../types/marketData.types';

/** List all tags for the current user. */
export async function listTags(): Promise<Tag[]> {
  const res = await apiClient.get<{ tags: Tag[] }>('/tags');
  return res.data.tags;
}

/** Create a new tag. */
export async function createTag(
  name: string,
  color: string,
  categoryId?: string,
): Promise<Tag> {
  const res = await apiClient.post<{ tag: Tag }>('/tags', {
    name,
    color,
    category_id: categoryId,
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
export async function deleteTag(
  id: string
): Promise<{ message: string; trades_updated: number }> {
  const res = await apiClient.delete<{
    message: string;
    trades_updated: number;
  }>(`/tags/${id}`);
  return res.data;
}

export async function moveTag(id: string, categoryId: string): Promise<Tag> {
  const res = await apiClient.put<{ tag: Tag }>(`/tags/${id}`, { category_id: categoryId });
  return res.data.tag;
}

export async function listTagCategories(): Promise<TagCategory[]> {
  const res = await apiClient.get<{ categories: TagCategory[] }>('/tags/categories');
  return res.data.categories;
}

export async function createTagCategory(name: string, color: string): Promise<TagCategory> {
  const res = await apiClient.post<{ category: TagCategory }>('/tags/categories', { name, color });
  return res.data.category;
}

export async function updateTagCategory(id: string, data: Partial<Pick<TagCategory, 'name' | 'color'>>): Promise<TagCategory> {
  const res = await apiClient.put<{ category: TagCategory }>(`/tags/categories/${id}`, data);
  return res.data.category;
}

export async function deleteTagCategory(id: string): Promise<void> {
  await apiClient.delete(`/tags/categories/${id}`);
}
