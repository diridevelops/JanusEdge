import { X } from 'lucide-react';
import { useCallback, useEffect } from 'react';

interface MediaLightboxProps {
  /** Presigned URL of the media asset. */
  url: string;
  /** MIME type — determines render element. */
  contentType: string;
  /** Original file name shown as caption. */
  filename: string;
  /** Called when the lightbox should close. */
  onClose: () => void;
}

/**
 * Full-viewport overlay that enlarges an image or
 * plays a video.  Closes on backdrop click or Escape.
 */
export function MediaLightbox({
  url,
  contentType,
  filename,
  onClose,
}: MediaLightboxProps) {
  const isVideo = contentType.startsWith('video/');

  // Close on Escape key
  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKey);
    // Prevent body scroll while open
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.body.style.overflow = '';
    };
  }, [handleKey]);

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`Preview of ${filename}`}
    >
      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute top-4 right-4 text-white/80 hover:text-white transition"
        aria-label="Close preview"
      >
        <X className="h-7 w-7" />
      </button>

      {/* Media content — stop click propagation so
          clicking content doesn't close the modal */}
      <div
        className="max-h-[90vh] max-w-[90vw] flex items-center justify-center"
        onClick={(e) => e.stopPropagation()}
      >
        {isVideo ? (
          <video
            src={url}
            controls
            autoPlay
            muted
            className="max-h-[85vh] max-w-[85vw] rounded-lg shadow-2xl"
          />
        ) : (
          <img
            src={url}
            alt={filename}
            className="max-h-[85vh] max-w-[85vw] rounded-lg shadow-2xl object-contain"
          />
        )}
      </div>

      {/* Caption */}
      <p className="absolute bottom-4 left-1/2 -translate-x-1/2 text-sm text-white/70 truncate max-w-[80vw]">
        {filename}
      </p>
    </div>
  );
}
