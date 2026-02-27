import {
  Film,
  ImagePlus,
  Loader2,
  Trash2,
  Upload,
} from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  deleteMedia,
  getMediaUrl,
  listMedia,
  uploadMedia,
} from '../../api/media.api';
import { useToast } from '../../hooks/useToast';
import type { MediaAttachment } from '../../types/media.types';
import { MediaLightbox } from '../ui/MediaLightbox';

interface TradeMediaProps {
  /** ID of the trade this section belongs to. */
  tradeId: string;
  /**
   * When true, renders as a narrow vertical sidebar:
   * scrollable thumbnail column + fixed dropzone at bottom.
   */
  compact?: boolean;
}

/** Cached presigned URLs keyed by media id. */
const urlCache = new Map<string, string>();

/**
 * Trade-detail media section.
 *
 * - Drag-and-drop / click-to-upload area
 * - Thumbnail grid for images; film-strip icon for videos
 * - Click thumbnail to enlarge/play
 * - Delete button per attachment
 */
export function TradeMedia({ tradeId, compact = false }: TradeMediaProps) {
  const { addToast } = useToast();

  const [items, setItems] = useState<MediaAttachment[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [lightbox, setLightbox] = useState<{
    url: string;
    contentType: string;
    filename: string;
  } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── fetch list ────────────────────────────────────
  const fetchMedia = useCallback(async () => {
    try {
      const data = await listMedia(tradeId);
      setItems(data);
    } catch {
      addToast('error', 'Failed to load media');
    } finally {
      setIsLoading(false);
    }
  }, [tradeId, addToast]);

  useEffect(() => {
    fetchMedia();
  }, [fetchMedia]);

  // ── upload ────────────────────────────────────────
  async function handleFiles(files: FileList | File[]) {
    setUploading(true);
    let success = 0;
    for (const file of Array.from(files)) {
      try {
        await uploadMedia(tradeId, file);
        success += 1;
      } catch (err: unknown) {
        const msg =
          (err as { response?: { data?: { error?: string } } })
            ?.response?.data?.error ?? 'Upload failed';
        addToast('error', `${file.name}: ${msg}`);
      }
    }
    if (success > 0) {
      addToast('success', `${success} file(s) uploaded`);
      await fetchMedia();
    }
    setUploading(false);
    // Reset the file input so the same file can be re-selected
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  // ── drag-and-drop handlers ────────────────────────
  function onDragOver(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(true);
  }
  function onDragLeave() {
    setIsDragging(false);
  }
  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length) {
      handleFiles(e.dataTransfer.files);
    }
  }

  // ── open lightbox ─────────────────────────────────
  async function handleOpen(item: MediaAttachment) {
    try {
      let url = urlCache.get(item.id);
      if (!url) {
        url = await getMediaUrl(item.id);
        urlCache.set(item.id, url);
      }
      setLightbox({
        url,
        contentType: item.content_type,
        filename: item.original_filename,
      });
    } catch {
      addToast('error', 'Failed to load media');
    }
  }

  // ── delete ────────────────────────────────────────
  async function handleDelete(
    e: React.MouseEvent,
    mediaId: string
  ) {
    e.stopPropagation();
    if (!confirm('Delete this attachment?')) return;
    try {
      await deleteMedia(mediaId);
      urlCache.delete(mediaId);
      setItems((prev) => prev.filter((m) => m.id !== mediaId));
      addToast('success', 'Attachment deleted');
    } catch {
      addToast('error', 'Failed to delete attachment');
    }
  }

  // ── thumbnail URL helper ──────────────────────────
  const [thumbUrls, setThumbUrls] = useState<
    Record<string, string>
  >({});

  useEffect(() => {
    let cancelled = false;
    async function loadThumbs() {
      const newUrls: Record<string, string> = {};
      for (const item of items) {
        // Only fetch thumbnails for images
        if (item.media_type !== 'image') continue;
        if (thumbUrls[item.id]) continue;
        try {
          let url = urlCache.get(item.id);
          if (!url) {
            url = await getMediaUrl(item.id);
            urlCache.set(item.id, url);
          }
          newUrls[item.id] = url;
        } catch {
          // ignore individual failures
        }
      }
      if (!cancelled && Object.keys(newUrls).length > 0) {
        setThumbUrls((prev) => ({ ...prev, ...newUrls }));
      }
    }
    loadThumbs();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  // ── render ────────────────────────────────────────

  // ── shared sub-components ─────────────────────────

  /** Dropzone — upload area. Compact mode is smaller. */
  const dropzone = (
    <div
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      onClick={() => fileInputRef.current?.click()}
      className={`
        flex flex-col items-center justify-center gap-1
        border-2 border-dashed rounded-lg cursor-pointer
        transition-colors shrink-0
        ${compact ? 'w-full h-16 lg:h-auto lg:aspect-square p-2' : 'p-6 gap-2'}
        ${
          isDragging
            ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20'
            : 'border-gray-300 dark:border-gray-600 hover:border-brand-400 dark:hover:border-brand-500'
        }
      `}
      role="button"
      tabIndex={0}
      aria-label="Upload media files"
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          fileInputRef.current?.click();
        }
      }}
    >
      {uploading ? (
        <Loader2 className={`text-brand-500 animate-spin ${compact ? 'h-5 w-5' : 'h-6 w-6'}`} />
      ) : (
        <Upload className={`text-gray-400 dark:text-gray-500 ${compact ? 'h-5 w-5' : 'h-6 w-6'}`} />
      )}
      {!compact && (
        <>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {uploading
              ? 'Uploading…'
              : 'Drag & drop or click to upload images / videos'}
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500">
            Max 500 MB per file · JPG, PNG, GIF, WebP, MP4, WebM, MOV
          </p>
        </>
      )}
      {compact && (
        <p className="text-[10px] text-gray-400 dark:text-gray-500 text-center leading-tight">
          {uploading ? 'Uploading…' : 'Upload'}
        </p>
      )}
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/webm,video/quicktime"
        multiple
        onChange={(e) => {
          if (e.target.files?.length) handleFiles(e.target.files);
        }}
      />
    </div>
  );

  /** Single thumbnail tile */
  const renderTile = (item: MediaAttachment) => (
    <div
      key={item.id}
      onClick={() => handleOpen(item)}
      className="
        group relative aspect-square rounded-lg overflow-hidden
        bg-gray-100 dark:bg-gray-800 cursor-pointer
        ring-1 ring-gray-200 dark:ring-gray-700
        hover:ring-brand-400 dark:hover:ring-brand-500
        transition shrink-0
      "
      role="button"
      tabIndex={0}
      aria-label={`Open ${item.original_filename}`}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleOpen(item);
        }
      }}
    >
      {item.media_type === 'image' ? (
        thumbUrls[item.id] ? (
          <img
            src={thumbUrls[item.id]}
            alt={item.original_filename}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <ImagePlus className="h-6 w-6 text-gray-400 dark:text-gray-500" />
          </div>
        )
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <Film className="h-8 w-8 text-gray-400 dark:text-gray-500" />
        </div>
      )}

      {/* Hover overlay with delete button */}
      <div className="
        absolute inset-0 bg-black/0 group-hover:bg-black/30
        flex items-start justify-end p-1.5 transition-colors
      ">
        <button
          onClick={(e) => handleDelete(e, item.id)}
          className="
            opacity-0 group-hover:opacity-100
            bg-red-600 hover:bg-red-700 text-white
            rounded-full p-1 transition-opacity
          "
          aria-label={`Delete ${item.original_filename}`}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Filename tooltip on bottom */}
      <p className="
        absolute bottom-0 inset-x-0 text-[10px]
        bg-black/50 text-white/90 px-1.5 py-0.5
        truncate opacity-0 group-hover:opacity-100
        transition-opacity
      ">
        {item.original_filename}
      </p>
    </div>
  );

  /** Lightbox portal */
  const lightboxPortal = lightbox
    ? createPortal(
        <MediaLightbox
          url={lightbox.url}
          contentType={lightbox.contentType}
          filename={lightbox.filename}
          onClose={() => setLightbox(null)}
        />,
        document.body
      )
    : null;

  // ── compact (sidebar) mode ────────────────────────
  if (compact) {
    return (
      <div className="flex flex-col h-full min-h-0">
        {/* Thumbnails: horizontal row on small screens, vertical column on lg+ */}
        <div className="
          flex-1 min-h-0 p-4
          flex flex-row gap-2 overflow-x-auto overflow-y-hidden
          lg:flex-col lg:overflow-x-hidden lg:overflow-y-auto lg:gap-2
        ">
          {isLoading && (
            <div className="flex justify-center py-4 w-full">
              <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
            </div>
          )}
          {!isLoading && items.map((item) => (
            <div key={item.id} className="w-20 shrink-0 lg:w-full">
              {renderTile(item)}
            </div>
          ))}
        </div>

        {/* Fixed dropzone at bottom — always visible */}
        <div className="shrink-0 p-4 pt-0">
          {dropzone}
        </div>

        {lightboxPortal}
      </div>
    );
  }

  // ── default (full-width) mode ─────────────────────
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 uppercase tracking-wider">
        Media ({items.length})
      </h3>

      {/* Upload area */}
      {dropzone}

      {/* Loading skeleton */}
      {isLoading && (
        <div className="flex justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
        </div>
      )}

      {/* Thumbnail grid */}
      {!isLoading && items.length > 0 && (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
          {items.map(renderTile)}
        </div>
      )}

      {lightboxPortal}
    </div>
  );
}
