import { isValidElement, type ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BacktestPositionOverlay, clampPositionStopPrice } from './BacktestPositionOverlay';
import type { BacktestOverlayPosition } from './BacktestPositionOverlay';

const hookHarness = vi.hoisted(() => ({
  stateIndex: 0,
  stateValues: [] as unknown[],
  effects: [] as Array<() => void | (() => void)>,
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
    useRef: () => ({ current: { getBoundingClientRect: () => ({ top: 0, height: 400 }) } }),
    useEffect: (effect: () => void | (() => void)) => {
      hookHarness.effects.push(effect);
    },
  };
});

interface ElementProps {
  className?: string;
  children?: unknown;
  style?: { top?: string | number; transform?: string };
  title?: string;
  onPointerDown?: (event: unknown) => void;
  onKeyDown?: (event: unknown) => void;
  onClick?: () => void;
  disabled?: boolean;
  role?: string;
  'aria-label'?: string;
  'data-position-id'?: string;
  'data-testid'?: string;
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
    id: 'position-A', side: 'long', remainingLots: 0.25, weightedEntryPrice: 100,
    stopLossPrice: 99, takeProfitPrice: 102, initialRiskUsd: 50,
    unrealizedPnlUsd: 25.5, stopMoved: false,
  },
  {
    id: 'position-B', side: 'short', remainingLots: 0.1, weightedEntryPrice: 105,
    stopLossPrice: 106, takeProfitPrice: 104, initialRiskUsd: 40,
    unrealizedPnlUsd: -8.75, stopMoved: true,
  },
  {
    id: 'position-C', side: 'long', remainingLots: 0.05, weightedEntryPrice: 102,
    stopLossPrice: 102, takeProfitPrice: 103, initialRiskUsd: 12,
    unrealizedPnlUsd: null, stopMoved: false,
  },
];

function makeOverlayProps(overrides: Partial<Parameters<typeof BacktestPositionOverlay>[0]> = {}) {
  return {
    positions,
    pricePrecision: 2,
    currentClose: 101,
    priceToCoordinate: (price: number) => 200 - price,
    coordinateToPrice: (y: number) => 200 - y,
    onMoveStop: vi.fn(),
    onMoveTarget: vi.fn(),
    onBreakEven: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
}

function renderOverlay(props = makeOverlayProps()) {
  hookHarness.stateIndex = 0;
  hookHarness.stateValues = [400, null, null];
  hookHarness.effects = [];
  return BacktestPositionOverlay(props);
}

function rerenderOverlay(props: ReturnType<typeof makeOverlayProps>) {
  hookHarness.stateIndex = 0;
  return BacktestPositionOverlay(props);
}

describe('Backtest position overlay', () => {
  beforeEach(() => {
    hookHarness.stateIndex = 0;
    hookHarness.stateValues = [400, null, null];
    hookHarness.effects = [];
  });

  afterEach(() => vi.unstubAllGlobals());

  it('keys each open position by its stable id and keeps entry levels non-draggable', () => {
    const root = renderOverlay();
    const elements = descendants(root);
    const positionContainers = elements.filter((element) => element.props['data-position-id']);
    const buttonLabels = elements
      .filter((element) => element.type === 'button')
      .map((element) => element.props['aria-label'] ?? '');

    expect(positionContainers.map((element) => element.props['data-position-id']))
      .toEqual(['position-A', 'position-B', 'position-C']);
    expect(buttonLabels.some((label) => label.includes('Move entry'))).toBe(false);
    expect(buttonLabels).toContain('Move stop-loss for position position-A, 99.00');
    expect(buttonLabels).toContain('Move take-profit for position position-B, 104.00');
    expect(textContent(root)).toContain('LONG - 0.250 lot @100.00 - P&L +1.00 price');
    expect(byLabel(root, 'long position controls for position-A').props['data-testid'])
      .toBe('position-entry-label-position-A');
    expect(byLabel(root, 'Move stop-loss for position position-A, 99.00').props.className)
      .toContain('left-0');
    expect(byLabel(root, 'Move take-profit for position position-B, 104.00').props.className)
      .toContain('left-0');
  });

  it('routes stop and target keyboard edits to only the named position and level', () => {
    const props = makeOverlayProps();
    const root = renderOverlay(props);
    const stopKey = byLabel(root, 'Move stop-loss for position position-A, 99.00').props.onKeyDown;
    const targetKey = byLabel(root, 'Move take-profit for position position-B, 104.00').props.onKeyDown;

    stopKey?.({ key: 'ArrowDown', preventDefault: vi.fn() });
    targetKey?.({ key: 'ArrowUp', preventDefault: vi.fn() });

    expect(props.onMoveStop).toHaveBeenCalledOnce();
    expect(props.onMoveStop).toHaveBeenCalledWith('position-A', 98.99);
    expect(props.onMoveTarget).toHaveBeenCalledOnce();
    expect(props.onMoveTarget).toHaveBeenCalledWith('position-B', 104.01);
  });

  it('clamps chart stop movement to the safe side of the current close, not entry', () => {
    expect(clampPositionStopPrice('long', 101.5, 100, 101, 2)).toBe(100.99);
    expect(clampPositionStopPrice('long', 100.25, 100, 101, 2)).toBe(100.25);
    expect(clampPositionStopPrice('short', 103.5, 105, 104, 2)).toBe(104.01);
    expect(clampPositionStopPrice('short', 104.5, 105, 104, 2)).toBe(104.5);
  });

  it('retains the entry-side bound if the current close is unavailable', () => {
    expect(clampPositionStopPrice('long', 100.5, 100, null, 2)).toBe(99.99);
    expect(clampPositionStopPrice('short', 104.5, 105, null, 2)).toBe(105.01);
  });

  it.each([
    {
      id: 'position-A', side: 'long' as const, entry: 100, stop: 99, close: 101,
      startY: 100, moveY: 98, expectedStop: 100.99,
    },
    {
      id: 'position-B', side: 'short' as const, entry: 105, stop: 106, close: 104,
      startY: 95, moveY: 97, expectedStop: 104.01,
    },
  ])('allows a $side stop to cross entry through chart dragging', ({ id, side, entry, stop, close, startY, moveY, expectedStop }) => {
    const position: BacktestOverlayPosition = {
      ...positions.find((item) => item.id === id)!,
      side,
      weightedEntryPrice: entry,
      stopLossPrice: stop,
    };
    const props = makeOverlayProps({ positions: [position], currentClose: close });
    const listeners = new Map<string, (event: PointerEvent) => void>();
    vi.stubGlobal('window', {
      addEventListener: (name: string, listener: EventListenerOrEventListenerObject) => {
        if (typeof listener === 'function') listeners.set(name, listener as (event: PointerEvent) => void);
      },
      removeEventListener: vi.fn(),
    });

    const initialRoot = renderOverlay(props);
    byLabel(initialRoot, `Move stop-loss for position ${id}, ${stop.toFixed(2)}`).props.onPointerDown?.({
      pointerId: 7,
      clientY: startY,
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    });

    rerenderOverlay(props);
    hookHarness.effects[hookHarness.effects.length - 1]?.();
    listeners.get('pointermove')?.({ pointerId: 7, clientY: moveY } as PointerEvent);
    rerenderOverlay(props);
    hookHarness.effects[hookHarness.effects.length - 1]?.();
    listeners.get('pointerup')?.({ pointerId: 7 } as PointerEvent);

    expect(props.onMoveStop).toHaveBeenCalledWith(id, expectedStop);
    expect(side === 'long' ? expectedStop > entry : expectedStop < entry).toBe(true);
  });

  it('allows long and short keyboard stop edits across entry', () => {
    const longPosition: BacktestOverlayPosition = { ...positions[0]!, stopLossPrice: 100 };
    const longProps = makeOverlayProps({ positions: [longPosition], currentClose: 101 });
    const longRoot = renderOverlay(longProps);
    byLabel(longRoot, 'Move stop-loss for position position-A, 100.00').props.onKeyDown?.({
      key: 'ArrowUp', preventDefault: vi.fn(),
    });
    expect(longProps.onMoveStop).toHaveBeenCalledWith('position-A', 100.01);

    const shortPosition: BacktestOverlayPosition = { ...positions[1]!, stopLossPrice: 105 };
    const shortProps = makeOverlayProps({ positions: [shortPosition], currentClose: 104.9 });
    const shortRoot = renderOverlay(shortProps);
    byLabel(shortRoot, 'Move stop-loss for position position-B, 105.00').props.onKeyDown?.({
      key: 'ArrowDown', preventDefault: vi.fn(),
    });
    expect(shortProps.onMoveStop).toHaveBeenCalledWith('position-B', 104.99);
  });

  it('blocks keyboard stop movement at the current-close guard', () => {
    const shortPosition: BacktestOverlayPosition = { ...positions[1]!, stopLossPrice: 104.01 };
    const props = makeOverlayProps({ positions: [shortPosition], currentClose: 104 });
    const root = renderOverlay(props);
    byLabel(root, 'Move stop-loss for position position-B, 104.01').props.onKeyDown?.({
      key: 'ArrowDown', preventDefault: vi.fn(),
    });
    expect(props.onMoveStop).toHaveBeenCalledWith('position-B', 104.01);
  });

  it('scopes break-even and close controls to their own ids and disables break-even when crossed', () => {
    const props = makeOverlayProps();
    const root = renderOverlay(props);

    byLabel(root, 'Move stop to break-even for position position-B').props.onClick?.();
    byLabel(root, 'Close position position-A').props.onClick?.();

    expect(props.onBreakEven).toHaveBeenCalledOnce();
    expect(props.onBreakEven).toHaveBeenCalledWith('position-B', 105);
    expect(props.onClose).toHaveBeenCalledOnce();
    expect(props.onClose).toHaveBeenCalledWith('position-A');
    expect(byLabel(root, 'Move stop to break-even for position position-C').props.disabled).toBe(true);
    expect(byLabel(root, 'Move stop to break-even for position position-A').props.disabled).toBe(false);
    expect(byLabel(root, 'Move stop to break-even for position position-A').props.className)
      .toContain('border-white/70');
    expect(byLabel(root, 'Close position position-A').props.className).toContain('bg-rose-700');
  });

  it('shows P&L and position controls inline at entry without a separate risk box', () => {
    const root = renderOverlay();
    const text = textContent(root);
    const entryGroups = descendants(root).filter((element) => element.props.role === 'group');

    expect(text).toContain('SHORT - 0.100 lot @105.00 - P&L +4.00 price');
    expect(text).toContain('P&L +4.00 price');
    expect(text).not.toMatch(/closed trade|journal/i);
    expect(descendants(root).some((element) => element.props.title === 'USD unrealized P&L unavailable'))
      .toBe(true);
    expect(entryGroups).toHaveLength(positions.length);
    expect(entryGroups.map((element) => element.props['aria-label'])).toEqual([
      'long position controls for position-A',
      'short position controls for position-B',
      'long position controls for position-C',
    ]);
    expect(descendants(root).some((element) => element.props.className?.includes('bg-slate-950/90')))
      .toBe(false);
  });

  it('marks instrument-unit P&L at the latest price while the chart shows an earlier close', () => {
    const root = renderOverlay(makeOverlayProps({
      positions: [positions[0]!],
      currentClose: 99,
      markPrice: 101.5,
      pipSize: 0.5,
      priceUnitLabel: 'pips',
    }));

    expect(textContent(root)).toContain('P&L +3.0 pips');
  });

  it('formats lots to the configured increment precision and orders entry P&L before USD P&L', () => {
    const displayPositions = [{ ...positions[0]!, remainingLots: 2, weightedEntryPrice: 341.946 }];
    const sharedDisplayProps = {
      positions: displayPositions,
      pricePrecision: 3,
      currentClose: 342.2,
      priceToCoordinate: (price: number) => 400 - price,
      pipSize: 0.01,
      priceUnitLabel: 'points',
    };
    const root = renderOverlay(makeOverlayProps({
      ...sharedDisplayProps,
      lotIncrement: 1,
    }));

    expect(textContent(root)).toContain('LONG - 2 lot @341.946 - P&L +25.4 pts.');

    const hundredthLotRoot = renderOverlay(makeOverlayProps({
      ...sharedDisplayProps,
      lotIncrement: 0.01,
    }));
    expect(textContent(hundredthLotRoot)).toContain('LONG - 2.00 lot @341.946 - P&L +25.4 pts.');
  });
});
