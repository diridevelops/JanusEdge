import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { filterInstrumentSearch } from '../../utils/instrumentSearch';

interface InstrumentComboboxProps {
  id: string;
  value: string;
  instruments: readonly string[];
  disabled?: boolean;
  placeholder?: string;
  onChange: (instrument: string) => void;
}

export function InstrumentCombobox({
  id,
  value,
  instruments,
  disabled = false,
  placeholder = 'Select an instrument',
  onChange,
}: InstrumentComboboxProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const activeOptionRef = useRef<HTMLLIElement>(null);
  const listboxId = `${id}-options`;

  const filteredInstruments = useMemo(
    () => filterInstrumentSearch(instruments, query, (instrument) => [instrument]),
    [instruments, query]
  );
  const activeOptionId = isOpen && filteredInstruments[activeIndex]
    ? `${listboxId}-${activeIndex}`
    : undefined;

  useEffect(() => {
    activeOptionRef.current?.scrollIntoView?.({ block: 'nearest' });
  }, [activeIndex, isOpen]);

  function openOptions() {
    setQuery('');
    setActiveIndex(Math.max(0, instruments.indexOf(value)));
    setIsOpen(true);
  }

  function closeOptions() {
    setQuery('');
    setIsOpen(false);
  }

  function selectInstrument(instrument: string) {
    onChange(instrument);
    closeOptions();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (!isOpen) {
        openOptions();
        return;
      }
      setActiveIndex((index) => Math.max(
        0,
        Math.min(filteredInstruments.length - 1, index + 1)
      ));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (!isOpen) {
        openOptions();
        return;
      }
      setActiveIndex((index) => Math.max(0, index - 1));
    } else if (event.key === 'Enter' && isOpen) {
      event.preventDefault();
      const activeInstrument = filteredInstruments[activeIndex];
      if (activeInstrument) selectInstrument(activeInstrument);
    } else if (event.key === 'Escape' && isOpen) {
      event.preventDefault();
      closeOptions();
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <input
        id={id}
        type="text"
        role="combobox"
        aria-autocomplete="list"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={isOpen && filteredInstruments.length ? listboxId : undefined}
        aria-activedescendant={activeOptionId}
        aria-required="true"
        autoComplete="off"
        value={isOpen ? query : value}
        onFocus={() => {
          if (!isOpen && !disabled) openOptions();
        }}
        onChange={(event) => {
          setQuery(event.currentTarget.value);
          setActiveIndex(0);
          setIsOpen(true);
        }}
        onKeyDown={handleKeyDown}
        onBlur={(event) => {
          const nextTarget = event.relatedTarget;
          if (!(nextTarget instanceof Node && rootRef.current?.contains(nextTarget))) {
            closeOptions();
          }
        }}
        disabled={disabled}
        placeholder={isOpen ? 'Search instruments…' : placeholder}
        className="input-field pr-10"
      />
      <ChevronDown
        aria-hidden="true"
        className={`pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
      />

      {isOpen && (
        <div className="absolute z-50 mt-1 max-h-60 w-full overflow-y-auto rounded-md border border-gray-300 bg-white shadow-lg dark:border-gray-600 dark:bg-gray-800">
          {filteredInstruments.length ? (
            <ul id={listboxId} role="listbox" aria-label="Available instruments" className="py-1">
              {filteredInstruments.map((instrument, index) => {
                const isSelected = instrument === value;
                const isActive = index === activeIndex;
                return (
                  <li
                    key={instrument}
                    id={`${listboxId}-${index}`}
                    ref={isActive ? activeOptionRef : undefined}
                    role="option"
                    aria-selected={isSelected}
                    onMouseEnter={() => setActiveIndex(index)}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => selectInstrument(instrument)}
                    className={`flex cursor-pointer items-center justify-between px-3 py-2 text-sm text-gray-900 dark:text-gray-100 ${isActive ? 'bg-blue-100 dark:bg-blue-900/50' : 'hover:bg-gray-100 dark:hover:bg-gray-700'}`}
                  >
                    <span>{instrument}</span>
                    {isSelected && <Check className="h-4 w-4 text-blue-600 dark:text-blue-400" aria-hidden="true" />}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p role="status" className="px-3 py-2 text-sm text-gray-500 dark:text-gray-400">
              No matching instruments.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
