import { Plus, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { createTag, listTags } from '../../api/tags.api';
import { updateTrade } from '../../api/trades.api';
import { useToast } from '../../hooks/useToast';
import type { Tag } from '../../types/marketData.types';

interface TagSelectorProps {
  /** Trade ID. */
  tradeId: string;
  /** Currently applied tag IDs. */
  tagIds: string[];
  /** Callback after a tag change is saved. */
  onChanged?: () => void;
}

/** Tag selector with create-new-tag ability. */
export function TagSelector({ tradeId, tagIds, onChanged }: TagSelectorProps) {
  const [tags, setTags] = useState<Tag[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [newTagName, setNewTagName] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const { addToast } = useToast();

  useEffect(() => {
    listTags().then(setTags).catch(() => {});
  }, []);

  const selectedTags = tags.filter((t) => tagIds.includes(t.id));
  const availableTags = tags.filter((t) => !tagIds.includes(t.id));

  async function addTag(tagId: string) {
    setIsSaving(true);
    try {
      await updateTrade(tradeId, { tag_ids: [...tagIds, tagId] });
      onChanged?.();
    } catch {
      addToast('error', 'Failed to add tag');
    } finally {
      setIsSaving(false);
    }
  }

  async function removeTag(tagId: string) {
    setIsSaving(true);
    try {
      await updateTrade(tradeId, {
        tag_ids: tagIds.filter((id) => id !== tagId),
      });
      onChanged?.();
    } catch {
      addToast('error', 'Failed to remove tag');
    } finally {
      setIsSaving(false);
    }
  }

  async function handleCreateTag() {
    if (!newTagName.trim()) return;
    setIsSaving(true);
    try {
      const newTag = await createTag(newTagName.trim(), '#6366f1');
      setTags((prev) => [...prev, newTag]);
      await addTag(newTag.id);
      setNewTagName('');
      setShowAdd(false);
    } catch {
      addToast('error', 'Failed to create tag');
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 uppercase tracking-wider">
        Tags
      </h3>

      {/* Applied tags */}
      <div className="flex flex-wrap gap-2">
        {selectedTags.map((tag) => (
          <span
            key={tag.id}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-brand-50 text-brand-700"
            style={tag.color ? { backgroundColor: `${tag.color}20`, color: tag.color } : undefined}
          >
            {tag.name}
            <button
              onClick={() => removeTag(tag.id)}
              disabled={isSaving}
              className="hover:opacity-70"
              aria-label={`Remove ${tag.name} tag`}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}

        {/* Add tag dropdown */}
        {!showAdd ? (
          <button
            onClick={() => setShowAdd(true)}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-400 dark:hover:bg-gray-600"
          >
            <Plus className="h-3 w-3" />
            Add Tag
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <select
              onChange={(e) => {
                if (e.target.value === '__new__') {
                  // Already in add mode, focus the input
                } else if (e.target.value) {
                  addTag(e.target.value);
                  setShowAdd(false);
                }
              }}
              className="input-field text-xs py-1 w-36"
              defaultValue=""
            >
              <option value="" disabled>Select tag...</option>
              {availableTags.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
              <option value="__new__">+ Create new...</option>
            </select>
            <button
              onClick={() => setShowAdd(false)}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      {/* New tag input */}
      {showAdd && (
        <div className="flex items-center gap-2 mt-2">
          <input
            type="text"
            placeholder="New tag name"
            value={newTagName}
            onChange={(e) => setNewTagName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreateTag()}
            className="input-field text-sm w-36"
            autoFocus
          />
          <button
            onClick={handleCreateTag}
            disabled={!newTagName.trim() || isSaving}
            className="btn-primary text-xs py-1.5 px-3"
          >
            Create
          </button>
        </div>
      )}
    </div>
  );
}
