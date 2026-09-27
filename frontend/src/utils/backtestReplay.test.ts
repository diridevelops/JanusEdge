import { describe, expect, it, vi } from 'vitest';
import type { ReplayController } from '@getcandlekit/charts';
import type { BacktestCandle, BacktestReplayPosition } from '../types/backtest.types';
import { aggregateRevealedCandles } from './backtestCandles';
import {
  createBacktestReplayDataSource,
  createCandleKitControlsAdapter,
  createReplayPositionWriter,
} from './backtestReplay';

const minute = 60_000;

function candle(timeMs: number): BacktestCandle {
  return {
    time_ms: timeMs,
    open: 1,
    high: 2,
    low: 0.5,
    close: 1.5,
    volume: 7,
  };
}

describe('createBacktestReplayDataSource', () => {
  it('maps the day API to UTC bars and returns dates nearest-first as CandleKit expects', async () => {
    const listDates = vi.fn(async () => ['2026-01-01', '2026-01-03', '2026-01-06']);
    const getCandles = vi.fn(async (_runId: string, date: string) => [
      candle(Date.parse(`${date}T00:00:00.000Z`)),
    ]);
    const source = createBacktestReplayDataSource(
      'run-1',
      { firstTimeMs: 0, lastTimeMs: Number.MAX_SAFE_INTEGER },
      { listCandleDates: listDates, getCandlesForDate: getCandles },
      2
    );

    await expect(source.listDatesBefore('EURUSD', '1m', '2026-01-06', 2))
      .resolves.toEqual(['2026-01-03', '2026-01-01']);
    await expect(source.listDatesAfter('EURUSD', '1m', '2026-01-01', 2))
      .resolves.toEqual(['2026-01-03', '2026-01-06']);
    await expect(source.fetchDay('EURUSD', '1m', '2026-01-03'))
      .resolves.toEqual([{
        ts: Date.parse('2026-01-03T00:00:00.000Z'),
        open: 1,
        high: 2,
        low: 0.5,
        close: 1.5,
        volume: 7,
      }]);
    expect(listDates).toHaveBeenCalledWith('run-1', { before: '2026-01-06' });
    expect(getCandles).toHaveBeenCalledTimes(1);
  });

  it('filters API rows outside the immutable snapshot bounds', async () => {
    const source = createBacktestReplayDataSource(
      'run-1',
      { firstTimeMs: minute, lastTimeMs: 2 * minute },
      {
        listCandleDates: async () => [],
        getCandlesForDate: async () => [candle(0), candle(minute), candle(2 * minute), candle(3 * minute)],
      }
    );

    await expect(source.fetchDay('EURUSD', '1m', '2026-01-01'))
      .resolves.toHaveLength(2);
  });
});

describe('createCandleKitControlsAdapter', () => {
  it('keeps prior-month source candles visible as context at the first replay candle', () => {
    const source = [candle(0), candle(minute), candle(2 * minute)];
    const visible = aggregateRevealedCandles(source, 1, 1);

    expect(visible.map((bar) => bar.ts)).toEqual([0, minute]);
  });

  it('excludes warm-up history from the replay progress window', () => {
    const getState = () => ({
      status: 'ready' as const,
      cursor: { ts: minute, seq: 1 },
      speed: 1,
      playing: false,
      window: { from: 0, to: 3 * minute },
      activeSeries: [],
      dataVersion: 1,
    });
    const controls = createCandleKitControlsAdapter(
      { getState } as unknown as ReplayController,
      [minute, 2 * minute, 3 * minute]
    );

    expect(controls.getState()).toMatchObject({
      status: 'ready',
      window: { from: minute, to: 3 * minute },
    });
  });

  it('pauses and snaps a slider timestamp forward to the next available candle', () => {
    const pause = vi.fn();
    const seek = vi.fn();
    const controller = { pause, seek } as unknown as ReplayController;
    const controls = createCandleKitControlsAdapter(controller, [0, minute, 5 * minute]);

    controls.seek(3 * minute);

    expect(pause).toHaveBeenCalledOnce();
    expect(seek).toHaveBeenCalledWith(5 * minute);
  });

  it('clamps a seek beyond the final candle to the completion cursor', () => {
    const seek = vi.fn();
    const controls = createCandleKitControlsAdapter(
      { pause: vi.fn(), seek } as unknown as ReplayController,
      [0, minute, 5 * minute]
    );

    controls.seek(6 * minute);

    expect(seek).toHaveBeenCalledWith(5 * minute);
  });

  it('clamps pre-start seeks and backward steps at the first replay candle', () => {
    const seek = vi.fn();
    const step = vi.fn();
    const pause = vi.fn();
    const controller = {
      pause,
      seek,
      step,
      getState: () => ({ status: 'ready', cursor: { ts: minute }, playing: false }),
    } as unknown as ReplayController;
    const controls = createCandleKitControlsAdapter(controller, [minute, 2 * minute]);

    controls.seek(0);
    controls.step(-1);

    expect(seek).toHaveBeenCalledWith(minute);
    expect(pause).toHaveBeenCalledTimes(2);
    expect(step).not.toHaveBeenCalled();
  });

  it('allows backward stepping after the selected replay has advanced', () => {
    const step = vi.fn();
    const controller = {
      pause: vi.fn(),
      seek: vi.fn(),
      step,
      getState: () => ({ status: 'ready', cursor: { ts: 2 * minute }, playing: false }),
    } as unknown as ReplayController;
    const controls = createCandleKitControlsAdapter(controller, [minute, 2 * minute]);

    controls.step(-1);

    expect(step).toHaveBeenCalledWith(-1);
  });
});

describe('createReplayPositionWriter', () => {
  it('serializes writes and coalesces queued cursor updates using each returned revision', async () => {
    let resolveFirst: ((position: BacktestReplayPosition) => void) | undefined;
    const save = vi.fn()
      .mockImplementationOnce(() => new Promise<BacktestReplayPosition>((resolve) => {
        resolveFirst = resolve;
      }))
      .mockImplementationOnce(async () => ({
        source_candle_index: 3,
        time_ms: 3 * minute,
        revision: 2,
      }));
    const writer = createReplayPositionWriter('run-1', 0, save);

    writer.enqueue({ source_candle_index: 1, time_ms: minute });
    writer.enqueue({ source_candle_index: 2, time_ms: 2 * minute });
    writer.enqueue({ source_candle_index: 3, time_ms: 3 * minute });
    resolveFirst?.({ source_candle_index: 1, time_ms: minute, revision: 1 });
    await writer.flush();

    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenNthCalledWith(1, 'run-1', {
      source_candle_index: 1,
      time_ms: minute,
      expected_revision: 0,
    });
    expect(save).toHaveBeenNthCalledWith(2, 'run-1', {
      source_candle_index: 3,
      time_ms: 3 * minute,
      expected_revision: 1,
    });
  });

  it('waits for a cursor queued while a route-exit flush is already waiting', async () => {
    let resolveFirst: ((position: BacktestReplayPosition) => void) | undefined;
    let resolveSecond: ((position: BacktestReplayPosition) => void) | undefined;
    const save = vi.fn()
      .mockImplementationOnce(() => new Promise<BacktestReplayPosition>((resolve) => {
        resolveFirst = resolve;
      }))
      .mockImplementationOnce(() => new Promise<BacktestReplayPosition>((resolve) => {
        resolveSecond = resolve;
      }));
    const writer = createReplayPositionWriter('run-1', 0, save);

    writer.enqueue({ source_candle_index: 1, time_ms: minute });
    const flushing = writer.flush();
    writer.enqueue({ source_candle_index: 2, time_ms: 2 * minute });
    resolveFirst?.({ source_candle_index: 1, time_ms: minute, revision: 1 });
    await Promise.resolve();
    expect(save).toHaveBeenCalledTimes(2);

    let flushed = false;
    void flushing.then(() => { flushed = true; });
    await Promise.resolve();
    expect(flushed).toBe(false);
    resolveSecond?.({ source_candle_index: 2, time_ms: 2 * minute, revision: 2 });
    await flushing;
    expect(flushed).toBe(true);
  });
});
