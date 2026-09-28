import { describe, expect, it, vi } from 'vitest';
import {
  createDrawingStateWriter,
  filterDrawingsAtReplayCursor,
  normalizeSerializedDrawingState,
  reconcileVisibleDrawingChanges,
  transformDrawingPrices,
} from './backtestDrawings';

describe('filterDrawingsAtReplayCursor', () => {
  it('normalizes drawing prices for display and retains canonical prices for saving', () => {
    const stored = JSON.stringify([
      { id: 'line', points: [{ time: 10, price: 25 }, { time: 11, price: 30 }] },
    ]);
    const displayed = transformDrawingPrices(stored, (price) => 100 * price / 25);
    const restored = transformDrawingPrices(displayed, (price) => price * 25 / 100);

    expect(JSON.parse(displayed)[0].points.map((point: { price: number }) => point.price))
      .toEqual([100, 120]);
    expect(JSON.parse(restored)[0].points.map((point: { price: number }) => point.price))
      .toEqual([25, 30]);
    expect(JSON.parse(stored)[0].points[0].price).toBe(25);
  });

  it('normalizes empty contract payloads to CandleKit arrays', () => {
    expect(normalizeSerializedDrawingState(null)).toBe('[]');
    expect(normalizeSerializedDrawingState('{}')).toBe('[]');
    expect(normalizeSerializedDrawingState('[{"id":"drawing"}]'))
      .toBe('[{"id":"drawing"}]');
    expect(() => normalizeSerializedDrawingState('{"drawings":[]}'))
      .toThrow('not a CandleKit drawing array');
  });

  it('hides drawings until every time anchor is at or before the cursor', () => {
    const savedState = JSON.stringify([
      {
        id: 'past-line',
        tool: 'TrendLine',
        points: [{ time: 10, price: 1 }, { time: 12, price: 2 }],
        style: {},
      },
      {
        id: 'future-line',
        tool: 'TrendLine',
        points: [{ time: 10, price: 1 }, { time: 20, price: 2 }],
        style: {},
      },
    ]);

    const visibleState = filterDrawingsAtReplayCursor(savedState, 15_000);

    expect(JSON.parse(visibleState).map((drawing: { id: string }) => drawing.id))
      .toEqual(['past-line']);
  });

  it('restores drawings at the cursor without changing the serialized state', () => {
    const savedState = JSON.stringify([
      {
        id: 'later-created-past-line',
        tool: 'TrendLine',
        points: [{ time: 10, price: 1 }, { time: 12, price: 2 }],
        style: {},
        createdAt: 100,
      },
      {
        id: 'future-line',
        tool: 'TrendLine',
        points: [{ time: 10, price: 1 }, { time: 20, price: 2 }],
        style: {},
      },
    ]);
    const originalCopy = savedState;

    const beforeAnchor = filterDrawingsAtReplayCursor(savedState, 19_999);
    const atAnchor = filterDrawingsAtReplayCursor(savedState, 20_000);

    expect(JSON.parse(beforeAnchor).map((drawing: { id: string }) => drawing.id))
      .toEqual(['later-created-past-line']);
    expect(JSON.parse(atAnchor).map((drawing: { id: string }) => drawing.id))
      .toEqual(['later-created-past-line', 'future-line']);
    expect(savedState).toBe(originalCopy);
    expect(JSON.parse(savedState)).toHaveLength(2);
  });

  it('merges visible edits and creations without dropping hidden future drawings', () => {
    const savedState = JSON.stringify([
      { id: 'past', points: [{ time: 10, price: 1 }], style: { color: 'blue' } },
      { id: 'future', points: [{ time: 20, price: 2 }], style: { color: 'red' } },
    ]);
    const editedAndCreated = JSON.stringify([
      { id: 'past', points: [{ time: 10, price: 3 }], style: { color: 'blue' } },
      { id: 'new', points: [{ time: 12, price: 4 }], style: { color: 'green' } },
    ]);

    const merged = reconcileVisibleDrawingChanges(
      savedState,
      editedAndCreated,
      new Set(['past'])
    );

    expect(JSON.parse(merged)).toEqual([
      { id: 'past', points: [{ time: 10, price: 3 }], style: { color: 'blue' } },
      { id: 'future', points: [{ time: 20, price: 2 }], style: { color: 'red' } },
      { id: 'new', points: [{ time: 12, price: 4 }], style: { color: 'green' } },
    ]);
    expect(JSON.parse(savedState)[0].points[0].price).toBe(1);
  });

  it('removes a deleted visible drawing and preserves hidden drawings', () => {
    const savedState = JSON.stringify([
      { id: 'visible', points: [{ time: 10, price: 1 }] },
      { id: 'future', points: [{ time: 20, price: 2 }] },
    ]);

    const merged = reconcileVisibleDrawingChanges(
      savedState,
      '[]',
      new Set(['visible'])
    );

    expect(JSON.parse(merged)).toEqual([
      { id: 'future', points: [{ time: 20, price: 2 }] },
    ]);
  });

  it('serializes coalesced writes using each confirmed revision', async () => {
    const requests: Array<{
      candlekit_version: string;
      schema_version: number;
      expected_revision: number;
      serialized_state: string;
    }> = [];
    const writer = createDrawingStateWriter({
      runId: 'run-1',
      intervalMinutes: 5,
      initialRevision: 3,
      debounceMs: 60_000,
      save: async (_runId, _interval, request) => {
        requests.push(request);
        return {
          interval_minutes: 5,
          candlekit_version: '0.1.0',
          schema_version: 1,
          revision: request.expected_revision + 1,
          serialized_state: request.serialized_state,
        };
      },
    });

    writer.enqueue('[{"id":"first"}]');
    const flushed = writer.flush();
    writer.enqueue('[{"id":"latest"}]');
    await flushed;

    expect(requests).toEqual([
      {
        candlekit_version: '0.1.0',
        schema_version: 1,
        expected_revision: 3,
        serialized_state: '[{"id":"first"}]',
      },
      {
        candlekit_version: '0.1.0',
        schema_version: 1,
        expected_revision: 4,
        serialized_state: '[{"id":"latest"}]',
      },
    ]);
    expect(writer.getRevision()).toBe(5);
  });

  it('surfaces revision conflicts and never retries with an overwrite', async () => {
    let rejectSave!: (error: unknown) => void;
    const save = vi.fn(() => new Promise<never>((_resolve, reject) => {
      rejectSave = reject;
    }));
    const onConflict = vi.fn();
    const writer = createDrawingStateWriter({
      runId: 'run-1',
      intervalMinutes: 5,
      initialRevision: 3,
      save,
      onConflict,
    });

    writer.enqueue('[]');
    const flushed = writer.flush();
    writer.enqueue('[{"id":"newer"}]');
    rejectSave({ response: { status: 409 } });
    await flushed;
    writer.enqueue('[{"id":"after-conflict"}]');
    await writer.flush();

    expect(save).toHaveBeenCalledTimes(1);
    expect(onConflict).toHaveBeenCalledTimes(1);
    expect(writer.isConflicted()).toBe(true);
    expect(writer.getRevision()).toBe(3);
  });

  it('reports an unconfirmed save to a panel-remount flush gate', async () => {
    const error = new Error('temporarily unavailable');
    const writer = createDrawingStateWriter({
      runId: 'run-1',
      intervalMinutes: 5,
      initialRevision: 0,
      save: async () => { throw error; },
    });
    writer.enqueue('[{"id":"pending"}]');

    await expect(writer.flushAndConfirm()).rejects.toBe(error);
  });
});
