import type {
  Bar,
  ReplayController,
  ReplayDataSource,
} from '@getcandlekit/charts';
import type {
  BacktestCandle,
  BacktestReplayPosition,
  BacktestReplayPositionRequest,
} from '../types/backtest.types';
import { findFirstCandleTimeAtOrAfter } from './backtestChartSync';

export interface BacktestReplayDataApi {
  listCandleDates(
    runId: string,
    params?: { before?: string; after?: string }
  ): Promise<string[]>;
  getCandlesForDate(runId: string, date: string): Promise<BacktestCandle[]>;
}

export interface BacktestReplayBounds {
  firstTimeMs: number;
  lastTimeMs: number;
}

/**
 * Adapt JanusEdge's date-addressed snapshot API to CandleKit's day source.
 * CandleKit asks for prior dates nearest-first; the API returns sorted dates.
 */
export function createBacktestReplayDataSource(
  runId: string,
  bounds: BacktestReplayBounds,
  api: BacktestReplayDataApi,
  maxConcurrentDays = 8
): ReplayDataSource {
  const dayCache = new Map<string, Promise<Bar[]>>();
  const dateCache = new Map<string, Promise<string[]>>();
  let activeDayRequests = 0;
  const pendingDayRequests: Array<() => void> = [];
  const dayRequestLimit = Math.max(1, Math.floor(maxConcurrentDays));

  async function acquireDaySlot(): Promise<void> {
    if (activeDayRequests < dayRequestLimit) {
      activeDayRequests += 1;
      return;
    }
    await new Promise<void>((resolve) => pendingDayRequests.push(resolve));
    activeDayRequests += 1;
  }

  function releaseDaySlot(): void {
    activeDayRequests -= 1;
    pendingDayRequests.shift()?.();
  }

  async function datesAround(
    direction: 'before' | 'after',
    date: string
  ): Promise<string[]> {
    const key = `${direction}:${date}`;
    let pending = dateCache.get(key);
    if (!pending) {
        pending = api.listCandleDates(runId, { [direction]: date }).catch((error: unknown) => {
          dateCache.delete(key);
          throw error;
        });
      dateCache.set(key, pending);
    }
    const dates = await pending;
    return dates.filter((candidate) => (
      direction === 'before' ? candidate < date : candidate > date
    )).sort();
  }

  return {
    async fetchDay(_symbol, _interval, date) {
      let pending = dayCache.get(date);
      if (!pending) {
        pending = (async () => {
          await acquireDaySlot();
          try {
            const candles = await api.getCandlesForDate(runId, date);
            return candles
              .filter((candle) => (
                candle.time_ms >= bounds.firstTimeMs
                && candle.time_ms <= bounds.lastTimeMs
              ))
              .sort((left, right) => left.time_ms - right.time_ms)
              .map((candle) => ({
                ts: candle.time_ms,
                open: candle.open,
                high: candle.high,
                low: candle.low,
                close: candle.close,
                ...(typeof candle.volume === 'number'
                  ? { volume: candle.volume }
                  : {}),
              }));
          } finally {
            releaseDaySlot();
          }
        })().catch((error: unknown) => {
          dayCache.delete(date);
          throw error;
        });
        dayCache.set(date, pending);
      }
      return pending;
    },

    async listDatesBefore(_symbol, _interval, date, count) {
      if (!Number.isInteger(count) || count <= 0) return [];
      const dates = await datesAround('before', date);
      return dates.filter((candidate) => candidate < date).reverse().slice(0, count);
    },

    async listDatesAfter(_symbol, _interval, date, count) {
      if (!Number.isInteger(count) || count <= 0) return [];
      const dates = await datesAround('after', date);
      return dates.filter((candidate) => candidate > date).slice(0, count);
    },
  };
}

function getReplayStepSize(speed: number | undefined): number {
  if (typeof speed !== 'number' || !Number.isFinite(speed) || speed <= 0) return 1;
  return Math.max(1, Math.round(speed));
}

/**
 * CandleKit's seek accepts arbitrary milliseconds and resumes a playing replay
 * after its asynchronous day lookup. JanusEdge seeks to the next available
 * candle and pauses, so adapt only that method for controls.
 */
export function createCandleKitControlsAdapter(
  controller: ReplayController,
  sortedCandleTimes: readonly number[],
  gatedActions?: {
    onAdvance: (selectedIndex: number, timeMs: number) => Promise<void>;
    onRewind: (selectedIndex: number, timeMs: number) => Promise<void>;
  }
): ReplayController {
  const firstEligibleTime = sortedCandleTimes[0];
  function boundState(state: ReturnType<ReplayController['getState']>) {
    if (
      state.status !== 'ready'
      || firstEligibleTime === undefined
      || state.window.from >= firstEligibleTime
    ) return state;
    return {
      ...state,
      window: { ...state.window, from: firstEligibleTime },
    };
  }

  if (gatedActions) {
    let playing = false;
    let pending = false;
    let speed = 1;
    let timer: number | null = null;
    const subscribers = new Set<Parameters<ReplayController['subscribe']>[0]>();
    let unsubscribeTarget: (() => void) | null = null;

    const currentState = () => {
      const state = boundState(controller.getState());
      return state.status === 'ready' ? { ...state, playing } : state;
    };
    const notify = () => {
      const state = currentState();
      subscribers.forEach((callback) => callback(state));
    };
    const stopTimer = () => {
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
    };
    const pause = () => {
      stopTimer();
      playing = false;
      controller.pause();
      notify();
    };
    const moveToIndex = async (index: number) => {
      if (pending || index < 0 || index >= sortedCandleTimes.length) return;
      const targetTime = sortedCandleTimes[index];
      if (targetTime === undefined) return;
      const state = controller.getState();
      if (state.status !== 'ready') return;
      const currentIndex = sortedCandleTimes.indexOf(state.cursor.ts);
      if (currentIndex === index) return;
      pending = true;
      try {
        if (index > currentIndex) await gatedActions.onAdvance(index, targetTime);
        else await gatedActions.onRewind(index, targetTime);
        controller.pause();
        controller.seek(targetTime);
      } catch {
        pause();
      } finally {
        pending = false;
        notify();
      }
    };
    const tick = async () => {
      if (!playing || pending) return;
      const tickStartedAt = Date.now();
      const state = controller.getState();
      if (state.status !== 'ready') {
        pause();
        return;
      }
      const currentIndex = sortedCandleTimes.indexOf(state.cursor.ts);
      if (currentIndex < 0 || currentIndex >= sortedCandleTimes.length - 1) {
        pause();
        return;
      }
      const stepSize = getReplayStepSize(speed);
      const nextIndex = Math.min(sortedCandleTimes.length - 1, currentIndex + stepSize);
      await moveToIndex(nextIndex);
      if (playing) {
        const elapsedMs = Date.now() - tickStartedAt;
        timer = window.setTimeout(() => void tick(), Math.max(0, 1_000 - elapsedMs));
      }
    };

    return new Proxy(controller, {
      get(target, property, receiver) {
        if (property === 'getState') return currentState;
        if (property === 'subscribe') {
          return (callback: Parameters<ReplayController['subscribe']>[0]) => {
            subscribers.add(callback);
            if (!unsubscribeTarget) {
              unsubscribeTarget = target.subscribe(() => notify());
            }
            callback(currentState());
            return () => {
              subscribers.delete(callback);
              if (subscribers.size === 0) {
                unsubscribeTarget?.();
                unsubscribeTarget = null;
              }
            };
          };
        }
        if (property === 'play') {
          return () => {
            if (playing) return;
            playing = true;
            notify();
            void tick();
          };
        }
        if (property === 'pause') return pause;
        if (property === 'setSpeed') {
          return (multiplier: number) => {
            if (Number.isFinite(multiplier) && multiplier > 0) speed = multiplier;
            target.setSpeed(multiplier);
            notify();
          };
        }
        if (property === 'seek') {
          return (timeMs: number) => {
            pause();
            const nextTime = findFirstCandleTimeAtOrAfter(sortedCandleTimes, timeMs);
            const snapped = nextTime ?? sortedCandleTimes[sortedCandleTimes.length - 1];
            if (snapped === undefined) return;
            void moveToIndex(sortedCandleTimes.indexOf(snapped));
          };
        }
        if (property === 'step') {
          return (direction: 1 | -1) => {
            pause();
            const state = target.getState();
            if (state.status !== 'ready') return;
            const currentIndex = sortedCandleTimes.indexOf(state.cursor.ts);
            const stepSize = getReplayStepSize(state.speed);
            const nextIndex = Math.max(
              0,
              Math.min(sortedCandleTimes.length - 1, currentIndex + direction * stepSize)
            );
            void moveToIndex(nextIndex);
          };
        }
        const value: unknown = Reflect.get(target, property, receiver);
        return typeof value === 'function' ? value.bind(target) : value;
      },
    });
  }

  return new Proxy(controller, {
    get(target, property, receiver) {
      if (property === 'getState') {
        return () => boundState(target.getState());
      }
      if (property === 'subscribe') {
        return (callback: Parameters<ReplayController['subscribe']>[0]) => (
          target.subscribe((state) => callback(boundState(state)))
        );
      }
      if (property === 'seek') {
        return (timeMs: number) => {
          const nextTime = findFirstCandleTimeAtOrAfter(sortedCandleTimes, timeMs);
          const snapped = nextTime ?? sortedCandleTimes[sortedCandleTimes.length - 1];
          if (snapped === undefined) return;
          target.pause();
          target.seek(snapped);
        };
      }
      if (property === 'step') {
        return (direction: 1 | -1) => {
          const initialState = target.getState();
          if (initialState.status !== 'ready') return;
          const firstIndex = firstEligibleTime === undefined
            ? 0
            : Math.max(0, sortedCandleTimes.indexOf(firstEligibleTime));
          const lastIndex = sortedCandleTimes.length - 1;
          const stepSize = getReplayStepSize(initialState.speed);
          const initialIndex = sortedCandleTimes.indexOf(initialState.cursor.ts);
          if (initialIndex < firstIndex || initialIndex > lastIndex) return;
          const remainingSteps = direction === 1
            ? lastIndex - initialIndex
            : initialIndex - firstIndex;
          if (remainingSteps <= 0) {
            if (direction === -1) target.pause();
            return;
          }

          for (let step = 0; step < Math.min(stepSize, remainingSteps); step += 1) {
            const state = target.getState();
            if (state.status !== 'ready') return;
            const currentIndex = sortedCandleTimes.indexOf(state.cursor.ts);
            const nextIndex = currentIndex + direction;
            if (
              currentIndex < firstIndex
              || currentIndex > lastIndex
              || nextIndex < firstIndex
              || nextIndex > lastIndex
            ) {
              if (direction === -1 && nextIndex < firstIndex) target.pause();
              return;
            }
            target.step(direction);
          }
        };
      }

      const value: unknown = Reflect.get(target, property, receiver);
      return typeof value === 'function' ? value.bind(target) : value;
    },
  });
}

export interface ReplayPositionChoice {
  source_candle_index: number;
  time_ms: number;
}

export type SaveReplayPosition = (
  runId: string,
  position: BacktestReplayPositionRequest
) => Promise<BacktestReplayPosition>;

/** Serialize cursor writes and keep only the newest choice queued behind an in-flight write. */
export function createReplayPositionWriter(
  runId: string,
  initialRevision: number,
  save: SaveReplayPosition,
  onError?: (error: unknown) => void,
  onSaved?: (position: BacktestReplayPosition) => void
) {
  let revision = initialRevision;
  let pending: ReplayPositionChoice | null = null;
  let draining: Promise<void> | null = null;
  const idleWaiters = new Set<() => void>();

  async function drain(): Promise<void> {
    while (pending) {
      const choice = pending;
      pending = null;
      try {
        const saved = await save(runId, {
          ...choice,
          expected_revision: revision,
        });
        revision = saved.revision;
        onSaved?.(saved);
      } catch (error: unknown) {
        onError?.(error);
        pending = null;
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
        if (pending) {
          void startDrain();
          return;
        }
        for (const resolve of idleWaiters) resolve();
        idleWaiters.clear();
      });
      draining = wrappedDrain;
    }
    return draining;
  }

  return {
    enqueue(choice: ReplayPositionChoice): void {
      pending = choice;
      void startDrain();
    },
    flush(): Promise<void> {
      if (pending && !draining) void startDrain();
      if (!pending && !draining) return Promise.resolve();
      return new Promise<void>((resolve) => idleWaiters.add(resolve));
    },
    getRevision(): number {
      return revision;
    },
  };
}
