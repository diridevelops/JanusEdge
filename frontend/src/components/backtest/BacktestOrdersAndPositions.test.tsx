import { isValidElement, type ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BacktestOrdersAndPositions } from './BacktestOrdersAndPositions';
import type { BacktestWorkingOrder } from './BacktestOrdersAndPositions';
import type { BacktestOverlayPosition } from './BacktestPositionOverlay';

const hookHarness = vi.hoisted(() => ({
  stateIndex: 0,
  stateValues: [] as unknown[],
}));

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>();
  return {
    ...actual,
    useState: (initial: unknown) => {
      const index = hookHarness.stateIndex++;
      if (hookHarness.stateValues[index] === undefined) hookHarness.stateValues[index] = initial;
      return [hookHarness.stateValues[index], (next: unknown) => {
        const current = hookHarness.stateValues[index];
        hookHarness.stateValues[index] = typeof next === 'function'
          ? (next as (previous: unknown) => unknown)(current)
          : next;
      }];
    },
    useEffect: () => undefined,
  };
});

interface ElementProps {
  children?: unknown;
  value?: string | number | readonly string[];
  disabled?: boolean;
  type?: string;
  onClick?: () => void;
  onChange?: (event: unknown) => void;
  onBlur?: () => void;
  'aria-label'?: string;
}

function descendants(node: unknown): Array<ReactElement<ElementProps>> {
  if (Array.isArray(node)) return node.flatMap(descendants);
  if (!isValidElement(node)) return [];
  const element = node as ReactElement<ElementProps>;
  return [element, ...descendants(element.props.children)];
}

function textContent(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textContent).join('');
  if (isValidElement(node)) return textContent((node as ReactElement<ElementProps>).props.children);
  return '';
}

function byLabel(root: unknown, label: string): ReactElement<ElementProps> {
  const element = descendants(root).find((candidate) => candidate.props['aria-label'] === label);
  if (!element) throw new Error(`Expected an element labeled "${label}"`);
  return element;
}

const positions: BacktestOverlayPosition[] = [
  {
    id: 'long-1', side: 'long', remainingLots: 0.25, weightedEntryPrice: 123.45,
    stopLossPrice: 123.4, takeProfitPrice: 123.55, initialRiskUsd: 12.5,
    unrealizedPnlUsd: 4.25, stopMoved: false,
  },
  {
    id: 'short-2', side: 'short', remainingLots: 0.1, weightedEntryPrice: 124.2,
    stopLossPrice: 124.25, takeProfitPrice: 124.1, initialRiskUsd: 5,
    unrealizedPnlUsd: null, stopMoved: true,
  },
];

const workingOrders: BacktestWorkingOrder[] = [
  {
    id: 'pending-7', side: 'buy', orderType: 'limit', lots: 0.2, entryPrice: 123.3,
    stopLossPrice: 123.2, takeProfitPrice: 123.5, projectedRiskUsd: 8.4,
  },
];

function makeProps(overrides: Partial<Parameters<typeof BacktestOrdersAndPositions>[0]> = {}) {
  return {
    workingOrders,
    positions,
    pricePrecision: 2,
    onCancelOrder: vi.fn(),
    onMoveStop: vi.fn(),
    onMoveTarget: vi.fn(),
    onBreakEven: vi.fn(),
    onClosePosition: vi.fn(),
    ...overrides,
  };
}

function renderList(props = makeProps()) {
  hookHarness.stateIndex = 0;
  return BacktestOrdersAndPositions(props);
}

describe('Backtest orders and positions', () => {
  beforeEach(() => {
    hookHarness.stateIndex = 0;
    hookHarness.stateValues = [];
  });

  it('cancels only the selected pending order', () => {
    const props = makeProps();
    const root = renderList(props);

    byLabel(root, 'Cancel pending order pending-7').props.onClick?.();

    expect(props.onCancelOrder).toHaveBeenCalledOnce();
    expect(props.onCancelOrder).toHaveBeenCalledWith('pending-7');
    expect(props.onMoveStop).not.toHaveBeenCalled();
    expect(props.onMoveTarget).not.toHaveBeenCalled();
    expect(props.onBreakEven).not.toHaveBeenCalled();
    expect(props.onClosePosition).not.toHaveBeenCalled();
  });

  it('keeps stop, target, break-even, and close callbacks isolated by position id', () => {
    const props = makeProps();
    const root = renderList(props);

    const longStop = byLabel(root, 'Stop price for position long-1');
    longStop.props.onChange?.({ currentTarget: { value: '123.39' } });
    const updatedAfterStopChange = renderList(props);
    byLabel(updatedAfterStopChange, 'Stop price for position long-1').props.onBlur?.();

    const shortTarget = byLabel(updatedAfterStopChange, 'Target price for position short-2');
    shortTarget.props.onChange?.({ currentTarget: { value: '124.08' } });
    const updatedAfterTargetChange = renderList(props);
    byLabel(updatedAfterTargetChange, 'Target price for position short-2').props.onBlur?.();
    byLabel(updatedAfterTargetChange, 'Move stop to break-even for position long-1').props.onClick?.();
    byLabel(updatedAfterTargetChange, 'Close position short-2').props.onClick?.();

    expect(props.onMoveStop).toHaveBeenCalledOnce();
    expect(props.onMoveStop).toHaveBeenCalledWith('long-1', 123.39);
    expect(props.onMoveTarget).toHaveBeenCalledOnce();
    expect(props.onMoveTarget).toHaveBeenCalledWith('short-2', 124.08);
    expect(props.onBreakEven).toHaveBeenCalledOnce();
    expect(props.onBreakEven).toHaveBeenCalledWith('long-1', 123.45);
    expect(props.onClosePosition).toHaveBeenCalledOnce();
    expect(props.onClosePosition).toHaveBeenCalledWith('short-2');
  });

  it.each([
    { id: 'long-1', close: 123.5, stop: '123.46' },
    { id: 'short-2', close: 124.0, stop: '124.1' },
  ])('accepts a $id stop beyond entry while it remains safe of the current close', ({ id, close, stop }) => {
    const props = makeProps({ positions: positions.filter((position) => position.id === id), currentClose: close });
    const label = `Stop price for position ${id}`;
    byLabel(renderList(props), label).props.onChange?.({ currentTarget: { value: stop } });
    byLabel(renderList(props), label).props.onBlur?.();

    expect(props.onMoveStop).toHaveBeenCalledOnce();
    expect(props.onMoveStop).toHaveBeenCalledWith(id, Number(stop));
  });

  it.each([
    { id: 'long-1', close: 123.5, stop: '123.5' },
    { id: 'short-2', close: 124.0, stop: '124.0' },
    { id: 'long-1', close: null, stop: '123.46' },
    { id: 'short-2', close: null, stop: '124.1' },
  ])('blocks unsafe or ungrounded $id stop edits', ({ id, close, stop }) => {
    const props = makeProps({ positions: positions.filter((position) => position.id === id), currentClose: close });
    const label = `Stop price for position ${id}`;
    byLabel(renderList(props), label).props.onChange?.({ currentTarget: { value: stop } });
    byLabel(renderList(props), label).props.onBlur?.();

    expect(props.onMoveStop).not.toHaveBeenCalled();
  });

  it('represents live exposure as open and never as a closed trade', () => {
    const content = textContent(renderList());

    expect(content).toContain('Open positions');
    expect(content).toContain('LONG · 0.250 lot');
    expect(content).toContain('SHORT · 0.100 lot');
    expect(content).not.toMatch(/closed trade|journal/i);
  });

  it('masks blind-mode price labels and does not expose raw prices in editable inputs', () => {
    const root = renderList(makeProps({ blindMode: true }));
    const content = textContent(root);
    const inputs = descendants(root).filter((element) => element.type === 'input');

    expect(content).toContain('••••••');
    expect(content).not.toContain('123.45');
    expect(content).not.toContain('123.40');
    expect(content).not.toContain('123.55');
    expect(inputs).toHaveLength(positions.length * 2);
    for (const [index, position] of positions.entries()) {
      const positionInputs = inputs.slice(index * 2, index * 2 + 2);
      const rawPrices = [position.stopLossPrice, position.takeProfitPrice].map(String);
      const eitherMaskedOrDisabled = positionInputs.every((input, level) => (
        input.props.disabled || String(input.props.value) !== rawPrices[level]
      ));
      expect(eitherMaskedOrDisabled).toBe(true);
    }
  });
});
