import type {
  BacktestDrawingState,
  BacktestSaveDrawingsRequest,
} from '../types/backtest.types';

interface DrawingAnchor {
  time: number;
}

interface SerializedDrawing {
  points: DrawingAnchor[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function getDrawingId(value: unknown): string | null {
  return isRecord(value) && typeof value.id === 'string' ? value.id : null;
}

function drawingIsVisible(value: unknown, cursorTimeSeconds: number): value is SerializedDrawing {
  if (!isRecord(value) || !Array.isArray(value.points)) {
    return false;
  }

  return value.points.every((point: unknown) => (
    isRecord(point)
    && typeof point.time === 'number'
    && Number.isFinite(point.time)
    && point.time <= cursorTimeSeconds
  ));
}

/**
 * Return a chart-only copy of CandleKit's serialized drawings that are visible
 * at the selected UTC cursor. CandleKit anchors use epoch seconds; the replay
 * cursor uses epoch milliseconds. The caller must retain and save the original
 * serialized state, never this filtered display copy.
 */
export function filterDrawingsAtReplayCursor(
  serializedState: string,
  cursorTimeMs: number
): string;
export function filterDrawingsAtReplayCursor(
  serializedState: null,
  cursorTimeMs: number
): null;
export function filterDrawingsAtReplayCursor(
  serializedState: string | null,
  cursorTimeMs: number
): string | null {
  if (serializedState === null) {
    return null;
  }

  if (!Number.isFinite(cursorTimeMs)) {
    return '[]';
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(serializedState);
  } catch {
    return serializedState;
  }

  if (!Array.isArray(parsed)) {
    return '[]';
  }

  const visible = parsed.filter((drawing) => drawingIsVisible(drawing, cursorTimeMs / 1_000));
  if (visible.length === parsed.length) {
    return serializedState;
  }
  return JSON.stringify(visible);
}

/** CandleKit 0.1.0 imports arrays; normalize the contract's empty object to one. */
export function normalizeSerializedDrawingState(serializedState: string | null): string {
  if (serializedState === null) return '[]';
  let parsed: unknown;
  try {
    parsed = JSON.parse(serializedState);
  } catch {
    throw new Error('The saved drawing state is not valid JSON.');
  }
  if (Array.isArray(parsed)) return serializedState;
  if (isRecord(parsed) && Object.keys(parsed).length === 0) return '[]';
  throw new Error('The saved drawing state is not a CandleKit drawing array.');
}

export function getDrawingIds(serializedState: string): string[] {
  try {
    const parsed: unknown = JSON.parse(serializedState);
    return Array.isArray(parsed)
      ? parsed.map(getDrawingId).filter((id): id is string => id !== null)
      : [];
  } catch {
    return [];
  }
}

/**
 * Merge an edited CandleKit display set into its full persisted set. Only the
 * ids that were present in the display snapshot may be replaced or removed;
 * drawings hidden because of a later time anchor remain authoritative.
 */
export function reconcileVisibleDrawingChanges(
  authoritativeState: string,
  nextVisibleState: string,
  previouslyVisibleIds: ReadonlySet<string>
): string {
  let authoritative: unknown;
  let nextVisible: unknown;
  try {
    authoritative = JSON.parse(authoritativeState);
    nextVisible = JSON.parse(nextVisibleState);
  } catch {
    return authoritativeState;
  }
  if (!Array.isArray(authoritative) || !Array.isArray(nextVisible)) {
    return authoritativeState;
  }

  const visibleById = new Map<string, unknown>();
  for (const drawing of nextVisible) {
    const id = getDrawingId(drawing);
    if (id !== null) visibleById.set(id, drawing);
  }

  const merged: unknown[] = [];
  const existingIds = new Set<string>();
  for (const drawing of authoritative) {
    const id = getDrawingId(drawing);
    if (id === null || !previouslyVisibleIds.has(id)) {
      merged.push(drawing);
      if (id !== null) existingIds.add(id);
      continue;
    }

    const replacement = visibleById.get(id);
    if (replacement !== undefined) {
      merged.push(replacement);
      visibleById.delete(id);
      existingIds.add(id);
    }
    // If a previously visible id disappeared from the engine, it was deleted.
  }

  for (const [id, drawing] of visibleById) {
    if (!existingIds.has(id)) merged.push(drawing);
  }

  return JSON.stringify(merged);
}

export type SaveDrawingState = (
  runId: string,
  intervalMinutes: number,
  request: BacktestSaveDrawingsRequest
) => Promise<BacktestDrawingState>;

function isRevisionConflict(error: unknown): boolean {
  if (!isRecord(error) || !isRecord(error.response)) return false;
  return error.response.status === 409;
}

/** Debounce and serialize drawing writes using the server's optimistic revision. */
export function createDrawingStateWriter(options: {
  runId: string;
  intervalMinutes: number;
  initialRevision: number;
  save: SaveDrawingState;
  debounceMs?: number;
  onConflict?: (error: unknown) => void;
  onError?: (error: unknown) => void;
  onSaved?: (state: BacktestDrawingState) => void;
}) {
  const {
    runId,
    intervalMinutes,
    save,
    onConflict,
    onError,
    onSaved,
  } = options;
  let revision = options.initialRevision;
  let pending: string | null = null;
  let draining: Promise<void> | null = null;
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let conflicted = false;
  let lastError: unknown | null = null;
  let flushRequested = false;
  const idleWaiters = new Set<() => void>();
  const debounceMs = Math.max(0, options.debounceMs ?? 400);

  function clearDebounce(): void {
    if (debounceTimer !== null) clearTimeout(debounceTimer);
    debounceTimer = null;
  }

  async function drain(): Promise<void> {
    while (pending !== null && debounceTimer === null && !conflicted) {
      const serializedState = pending;
      pending = null;
      try {
        const saved = await save(runId, intervalMinutes, {
          candlekit_version: '0.1.0',
          schema_version: 1,
          expected_revision: revision,
          serialized_state: serializedState,
        });
        revision = saved.revision;
        lastError = null;
        onSaved?.(saved);
      } catch (error: unknown) {
        pending = null;
        lastError = error;
        if (isRevisionConflict(error)) {
          conflicted = true;
          onConflict?.(error);
        } else {
          onError?.(error);
        }
        break;
      }
    }
  }

  function startDrain(): Promise<void> {
    if (!draining) {
      const activeDrain = drain();
      const wrappedDrain = activeDrain.finally(() => {
        if (draining !== wrappedDrain) return;
        draining = null;
        if (pending !== null && !conflicted) {
          if (flushRequested) clearDebounce();
          if (debounceTimer === null) {
            void startDrain();
            return;
          }
          return;
        }
        flushRequested = false;
        for (const resolve of idleWaiters) resolve();
        idleWaiters.clear();
      });
      draining = wrappedDrain;
    }
    return draining;
  }

  function flush(): Promise<void> {
    clearDebounce();
    if (pending !== null && !draining && !conflicted) void startDrain();
    if (pending === null && !draining) return Promise.resolve();
    flushRequested = true;
    return new Promise<void>((resolve) => idleWaiters.add(resolve));
  }

  return {
    enqueue(serializedState: string): void {
      if (conflicted) return;
      lastError = null;
      pending = serializedState;
      clearDebounce();
      if (flushRequested) {
        void startDrain();
        return;
      }
      debounceTimer = setTimeout(() => {
        debounceTimer = null;
        void startDrain();
      }, debounceMs);
    },
    flush,
    async flushAndConfirm(): Promise<void> {
      await flush();
      if (lastError !== null) {
        throw lastError instanceof Error
          ? lastError
          : new Error('The drawing save was not confirmed.');
      }
    },
    isConflicted(): boolean {
      return conflicted;
    },
    hasPending(): boolean {
      return pending !== null;
    },
    getRevision(): number {
      return revision;
    },
  };
}
