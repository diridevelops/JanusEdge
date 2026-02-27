import { Info } from 'lucide-react';
import { useRef, useState } from 'react';

interface InfoTooltipProps {
  /** Tooltip text (supports newlines via \n). */
  text: string;
  /** Accessible label for the button (defaults to "More info"). */
  ariaLabel?: string;
  /** Icon size class (defaults to "w-3.5 h-3.5"). */
  iconSize?: string;
  /** Tailwind width class for the tooltip bubble (defaults to "w-56"). */
  widthClass?: string;
}

/**
 * Reusable info-icon button with a fixed-position tooltip popover.
 * Viewport-aware: clamps horizontally so the tooltip never overflows.
 */
export function InfoTooltip({
  text,
  ariaLabel = 'More info',
  iconSize = 'w-3.5 h-3.5',
  widthClass = 'w-56',
}: InfoTooltipProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const btnRef = useRef<HTMLButtonElement | null>(null);

  // Pixel width lookup for common Tailwind width classes
  const widthPx: Record<string, number> = {
    'w-48': 192,
    'w-56': 224,
    'w-64': 256,
    'w-72': 288,
    'w-80': 320,
  };

  function openTip() {
    const rect = btnRef.current?.getBoundingClientRect();
    if (rect) {
      const tipW = widthPx[widthClass] ?? 224;
      let left = rect.left + rect.width / 2;
      // Clamp so the tooltip stays inside the viewport
      left = Math.max(tipW / 2 + 8, Math.min(left, globalThis.innerWidth - tipW / 2 - 8));
      setPos({ top: rect.top - 8, left });
    }
    setOpen(true);
  }

  return (
    <span className="relative inline-flex">
      <button
        ref={btnRef}
        type="button"
        className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-colors"
        onMouseEnter={openTip}
        onMouseLeave={() => setOpen(false)}
        onFocus={openTip}
        onBlur={() => setOpen(false)}
        aria-label={ariaLabel}
      >
        <Info className={iconSize} strokeWidth={2.25} />
      </button>
      {open && (
        <div
          className={`fixed z-[120] ${widthClass} max-w-[80vw] px-3 py-2 text-xs text-gray-100 bg-gray-800 dark:bg-gray-700 rounded-lg shadow-lg whitespace-pre-line pointer-events-none`}
          style={{ top: pos.top, left: pos.left, transform: 'translate(-50%, -100%)' }}
        >
          {text}
          <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-x-4 border-x-transparent border-t-4 border-t-gray-800 dark:border-t-gray-700" />
        </div>
      )}
    </span>
  );
}
