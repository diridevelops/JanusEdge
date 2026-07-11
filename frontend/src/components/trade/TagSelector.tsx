import { Plus, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { createTag, listTagCategories, listTags } from '../../api/tags.api';
import { updateTrade } from '../../api/trades.api';
import { useToast } from '../../hooks/useToast';
import type { Tag, TagCategory } from '../../types/marketData.types';

interface TagSelectorProps { tradeId: string; tagIds: string[]; onChanged?: () => void; }

/** Category-grouped trade tag selector. */
export function TagSelector({ tradeId, tagIds, onChanged }: TagSelectorProps) {
  const [tags, setTags] = useState<Tag[]>([]);
  const [categories, setCategories] = useState<TagCategory[]>([]);
  const [addingTo, setAddingTo] = useState<string | null>(null);
  const [newName, setNewName] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const { addToast } = useToast();

  useEffect(() => {
    Promise.all([listTags(), listTagCategories()]).then(([loadedTags, loadedCategories]) => {
      setTags(loadedTags); setCategories(loadedCategories);
    }).catch(() => {});
  }, []);

  async function saveTagIds(nextIds: string[]) {
    setIsSaving(true);
    try { await updateTrade(tradeId, { tag_ids: nextIds }); onChanged?.(); }
    catch { addToast('error', 'Failed to update tags'); }
    finally { setIsSaving(false); }
  }

  async function createInCategory(category: TagCategory) {
    if (!newName.trim()) return;
    setIsSaving(true);
    try {
      const tag = await createTag(newName.trim(), category.color, category.id);
      setTags((current) => [...current, { ...tag, category_id: category.id, category_name: category.name, category_color: category.color }]);
      await updateTrade(tradeId, { tag_ids: [...tagIds, tag.id] });
      onChanged?.(); setNewName(''); setAddingTo(null);
    } catch { addToast('error', 'Failed to create tag'); }
    finally { setIsSaving(false); }
  }

  return <div className="space-y-4">
    <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 uppercase tracking-wider">Tags</h3>
    {categories.map((category) => {
      const categoryTags = tags.filter((tag) => tag.category_id === category.id);
      const selected = categoryTags.filter((tag) => tagIds.includes(tag.id));
      const available = categoryTags.filter((tag) => !tagIds.includes(tag.id));
      return <section key={category.id} className="rounded-md border border-gray-200 p-3 dark:border-gray-700">
        <h4 className="mb-2 text-xs font-semibold uppercase" style={{ color: category.color }}>{category.name}</h4>
        <div className="flex flex-wrap gap-2">
          {selected.map((tag) => <span key={tag.id} className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium" style={{ backgroundColor: `${category.color}20`, color: category.color }}>{tag.name}<button onClick={() => void saveTagIds(tagIds.filter((id) => id !== tag.id))} disabled={isSaving}><X className="h-3 w-3" /></button></span>)}
          {available.length > 0 && <select className="input-field w-36 py-1 text-xs" defaultValue="" onChange={(event) => { if (event.target.value) void saveTagIds([...tagIds, event.target.value]); event.currentTarget.value = ''; }}><option value="">Add existing…</option>{available.map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}</select>}
          <button onClick={() => setAddingTo(category.id)} className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-xs dark:bg-gray-700"><Plus className="h-3 w-3" />Add Tag</button>
        </div>
        {addingTo === category.id && <div className="mt-2 flex gap-2"><input className="input-field w-36 py-1 text-sm" autoFocus value={newName} onChange={(event) => setNewName(event.target.value)} placeholder="New tag name" /><button className="btn-primary px-3 py-1 text-xs" disabled={isSaving} onClick={() => void createInCategory(category)}>Create</button><button onClick={() => setAddingTo(null)}><X className="h-4 w-4" /></button></div>}
      </section>;
    })}
  </div>;
}
