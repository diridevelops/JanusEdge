import type {
  ForexSymbolMappingEntry,
  InstrumentSizingMappingEntry,
  SymbolMappings,
} from '../types/auth.types';

export type ManualTradeInstrumentMapping =
  | InstrumentSizingMappingEntry
  | ForexSymbolMappingEntry;

export interface ManualTradeInstrumentResolution {
  canonicalSymbol: string;
  mapping: ManualTradeInstrumentMapping;
  source: 'settings' | 'legacy_forex';
  supported: boolean;
}

function symbolCandidates(symbol: string): string[] {
  const normalized = symbol.trim().toUpperCase();
  return Array.from(new Set([
    normalized,
    normalized.replace(/\//g, '-'),
    normalized.replace(/-/g, '/'),
  ].filter(Boolean)));
}

function findMapping<T>(
  mappings: Record<string, T> | undefined,
  candidates: string[],
): [string, T] | null {
  if (!mappings) return null;
  const byCode = new Map(
    Object.entries(mappings).map(([code, mapping]) => [
      code.trim().toUpperCase(),
      [code, mapping] as [string, T],
    ]),
  );
  for (const candidate of candidates) {
    const found = byCode.get(candidate);
    if (found) return found;
  }
  return null;
}

function hasPositiveNumber(value: number | null | undefined): boolean {
  return value != null && Number.isFinite(value) && value > 0;
}

function isCompleteSettingsMapping(
  mapping: ManualTradeInstrumentMapping,
): boolean {
  return Boolean(
    mapping.supported_for_simulation !== false
    && mapping.base_currency
    && mapping.quote_currency
    && hasPositiveNumber(mapping.pip_size)
    && hasPositiveNumber(mapping.tick_size)
    && mapping.price_precision != null
    && Number.isInteger(mapping.price_precision)
    && mapping.price_precision >= 0
    && hasPositiveNumber(mapping.contract_size)
    && hasPositiveNumber(mapping.min_lots)
    && hasPositiveNumber(mapping.lot_increment),
  );
}

function isCompleteLegacyForexMapping(
  mapping: ForexSymbolMappingEntry,
): boolean {
  return Boolean(
    hasPositiveNumber(mapping.pip_size)
    && mapping.price_precision >= 0
    && Number.isInteger(mapping.price_precision)
    && hasPositiveNumber(mapping.contract_size)
    && mapping.base_currency
    && mapping.quote_currency,
  );
}

/** Resolve a Settings instrument code or its slash/dash alias exactly. */
export function resolveManualTradeInstrument(
  symbol: string,
  mappings: SymbolMappings | null | undefined,
): ManualTradeInstrumentResolution | null {
  const candidates = symbolCandidates(symbol);
  if (candidates.length === 0 || !mappings) return null;

  const settingsMatch = findMapping(
    mappings.instruments,
    candidates,
  );
  if (settingsMatch) {
    return {
      canonicalSymbol: settingsMatch[0],
      mapping: settingsMatch[1],
      source: 'settings',
      supported: isCompleteSettingsMapping(settingsMatch[1]),
    };
  }

  const forexMatch = findMapping(mappings.forex, candidates);
  if (!forexMatch) return null;
  return {
    canonicalSymbol: forexMatch[0],
    mapping: forexMatch[1],
    source: 'legacy_forex',
    supported: isCompleteLegacyForexMapping(forexMatch[1]),
  };
}

export function manualTradeLotMinimum(
  resolution: ManualTradeInstrumentResolution,
): number {
  return resolution.mapping.min_lots
    ?? (resolution.source === 'legacy_forex' ? 0.001 : 0);
}

export function manualTradeLotIncrement(
  resolution: ManualTradeInstrumentResolution,
): number {
  return resolution.mapping.lot_increment
    ?? (resolution.source === 'legacy_forex' ? 0.001 : 1);
}

export function manualTradeTickSize(
  resolution: ManualTradeInstrumentResolution,
): number {
  const tickSize = resolution.mapping.tick_size;
  if (tickSize != null && hasPositiveNumber(tickSize)) return tickSize;
  const precision = resolution.mapping.price_precision;
  return precision != null && precision >= 0
    ? 10 ** -precision
    : 0.01;
}
