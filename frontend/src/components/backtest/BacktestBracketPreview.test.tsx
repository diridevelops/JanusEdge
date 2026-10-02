import { isValidElement, type ReactElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { BacktestBracketPreview, type BacktestBracketPreviewProps } from './BacktestBracketPreview';
import { createDefaultBacktestBracket } from './backtestBracketMath';

const hookHarness = vi.hoisted(() => ({
  stateIndex: 0,
  stateValues: [] as unknown[],
  effects: [] as Array<() => void | (() => void)>,
  layer: null as null | { getBoundingClientRect: () => { top: number } },
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
    useRef: (initial: unknown) => ({ current: hookHarness.layer ?? initial }),
    useEffect: (effect: () => void | (() => void)) => {
      hookHarness.effects.push(effect);
    },
  };
});

interface PreviewElementProps {
  className?: string;
  children?: unknown;
  style?: Record<string, unknown>;
  onPointerDown?: (event: unknown) => void;
  onKeyDown?: (event: unknown) => void;
  onClick?: () => void;
  'aria-label'?: string;
  disabled?: boolean;
}

function descendants(node: unknown): Array<ReactElement<PreviewElementProps>> {
  if (Array.isArray(node)) return node.flatMap(descendants);
  if (!isValidElement(node)) return [];
  const element = node as ReactElement<PreviewElementProps>;
  return [element, ...descendants(element.props.children)];
}

function elementByClass(root: unknown, className: string): ReactElement<PreviewElementProps> {
  const element = descendants(root).find((candidate) => candidate.props.className?.split(' ').includes(className));
  if (!element) throw new Error(`Could not find preview element with class ${className}`);
  return element;
}

function elementByLabel(root: unknown, labelPrefix: string): ReactElement<PreviewElementProps> {
  const element = descendants(root).find((candidate) => candidate.props['aria-label']?.startsWith(labelPrefix));
  if (!element) throw new Error(`Could not find preview element with accessible label starting ${labelPrefix}`);
  return element;
}

function makePreviewProps(overrides: Partial<BacktestBracketPreviewProps> = {}): BacktestBracketPreviewProps {
  return {
    visible: true,
    entryType: 'limit',
    direction: 'long',
    entryPrice: 100,
    stopLossPrice: 99.9,
    takeProfitPrice: 100.1,
    pricePrecision: 2,
    pipSize: 0.01,
    quantityLots: 0.25,
    autoSize: true,
    riskBudgetUsd: 100,
    projectedRiskUsd: 25,
    projectedRewardUsd: 25,
    riskRewardRatio: 1,
    currentBalanceUsd: 10_000,
    canPlaceOrder: true,
    priceToCoordinate: (price) => 180 - (price - 100) * 100,
    coordinateToPrice: (y) => 100 + (180 - y) / 100,
    plotLeftPx: 40,
    plotRightPx: 360,
    onEntryPriceChange: vi.fn(),
    onStopLossPriceChange: vi.fn(),
    onTakeProfitPriceChange: vi.fn(),
    onPlaceOrder: vi.fn(),
    onCancel: vi.fn(),
    ...overrides,
  };
}

function prepareHooks() {
  hookHarness.stateIndex = 0;
  hookHarness.stateValues = [{ width: 420, height: 280 }, null];
  hookHarness.effects = [];
  hookHarness.layer = { getBoundingClientRect: () => ({ top: 0 }) };
}

function renderPreview(props: BacktestBracketPreviewProps) {
  hookHarness.stateIndex = 0;
  hookHarness.effects = [];
  return BacktestBracketPreview(props);
}

function withPointerWindow(run: (listeners: Map<string, EventListener>) => void) {
  const originalDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'window');
  const listeners = new Map<string, EventListener>();
  const mockWindow = {
    addEventListener: (type: string, listener: EventListenerOrEventListenerObject) => {
      if (typeof listener === 'function') listeners.set(type, listener);
    },
    removeEventListener: (type: string) => listeners.delete(type),
  } as unknown as Window;
  Object.defineProperty(globalThis, 'window', { configurable: true, value: mockWindow });
  try {
    run(listeners);
  } finally {
    if (originalDescriptor) Object.defineProperty(globalThis, 'window', originalDescriptor);
    else Reflect.deleteProperty(globalThis, 'window');
  }
}

function pointerEvent(pointerId: number, clientY: number) {
  return {
    pointerId,
    clientY,
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
  };
}

function installDragEffect() {
  const effect = hookHarness.effects[hookHarness.effects.length - 1];
  if (!effect) throw new Error('Expected the active drag effect to be registered.');
  const cleanup = effect();
  return typeof cleanup === 'function' ? cleanup : () => undefined;
}

describe('Backtest bracket preview', () => {
  beforeEach(() => prepareHooks());

  it('renders a draggable limit bracket with submit and cancel controls at the entry level', () => {
    const root = renderPreview(makePreviewProps());
    const elements = descendants(root);

    expect(elementByLabel(root, 'Move complete limit bracket')).toBeDefined();
    expect(elementByLabel(root, 'Move limit entry and complete bracket')).toBeDefined();
    expect(elementByLabel(root, 'Move stop-loss')).toBeDefined();
    expect(elementByLabel(root, 'Move take-profit')).toBeDefined();
    expect(elements.some((element) => element.props.className?.includes('zone--reward'))).toBe(true);
    expect(elements.some((element) => element.props.className?.includes('zone--risk'))).toBe(true);
    expect(elements.some((element) => element.props.className?.includes('selection-frame'))).toBe(true);
    expect(elements.some((element) => element.props.className?.includes('preview-summary'))).toBe(true);
    const actions = elementByClass(root, 'backtest-bracket-preview-actions');
    expect(actions.props.style?.top).toBe(180);
    expect(actions.props.style?.transform).toBe('translateY(-50%)');
    expect(elementByClass(root, 'backtest-bracket-preview-submit').props.children).toBe('Submit');
    expect(elementByClass(root, 'backtest-bracket-preview-cancel').props.children).toBe('Cancel');
  });

  it('moves a limit entry, stop, and target together while preserving their offsets', () => {
    const props = makePreviewProps();
    const entryChange = props.onEntryPriceChange as ReturnType<typeof vi.fn>;
    const stopChange = props.onStopLossPriceChange as ReturnType<typeof vi.fn>;
    const targetChange = props.onTakeProfitPriceChange as ReturnType<typeof vi.fn>;
    const initial = renderPreview(props);
    const group = elementByLabel(initial, 'Move complete limit bracket');
    group.props.onPointerDown?.(pointerEvent(7, 180));

    withPointerWindow((listeners) => {
      renderPreview(props);
      const cleanup = installDragEffect();
      listeners.get('pointermove')?.({ pointerId: 7, clientY: 160 } as unknown as Event);
      cleanup();
    });

    expect(entryChange).toHaveBeenLastCalledWith(100.2);
    expect(stopChange).toHaveBeenLastCalledWith(100.1);
    expect(targetChange).toHaveBeenLastCalledWith(100.3);
  });

  it('lets stop-loss and take-profit move independently', () => {
    const props = makePreviewProps();
    const entryChange = props.onEntryPriceChange as ReturnType<typeof vi.fn>;
    const stopChange = props.onStopLossPriceChange as ReturnType<typeof vi.fn>;
    const targetChange = props.onTakeProfitPriceChange as ReturnType<typeof vi.fn>;

    let root = renderPreview(props);
    elementByLabel(root, 'Move stop-loss').props.onPointerDown?.(pointerEvent(8, 190));
    withPointerWindow((listeners) => {
      renderPreview(props);
      const cleanup = installDragEffect();
      listeners.get('pointermove')?.({ pointerId: 8, clientY: 200 } as unknown as Event);
      cleanup();
    });
    expect(stopChange).toHaveBeenLastCalledWith(99.8);
    expect(entryChange).not.toHaveBeenCalled();
    expect(targetChange).not.toHaveBeenCalled();

    prepareHooks();
    root = renderPreview(props);
    elementByLabel(root, 'Move take-profit').props.onPointerDown?.(pointerEvent(9, 170));
    withPointerWindow((listeners) => {
      renderPreview(props);
      const cleanup = installDragEffect();
      listeners.get('pointermove')?.({ pointerId: 9, clientY: 160 } as unknown as Event);
      cleanup();
    });
    expect(targetChange).toHaveBeenLastCalledWith(100.2);
    expect(entryChange).not.toHaveBeenCalled();
    expect(stopChange).toHaveBeenCalledTimes(1);
  });

  it('keeps market entry fixed at the revealed close while allowing protection edits', () => {
    const props = makePreviewProps({ entryType: 'market' });
    const root = renderPreview(props);
    const elements = descendants(root);

    expect(elementByClass(root, 'backtest-bracket-preview-market-entry').props['aria-label'])
      .toContain('fixed at the current revealed close 100.00');
    expect(elements.some((element) => element.props.className?.includes('dragline--entry'))).toBe(false);
    expect(elements.some((element) => element.props.className?.includes('group-drag'))).toBe(false);

    const entryChange = props.onEntryPriceChange as ReturnType<typeof vi.fn>;
    const stopChange = props.onStopLossPriceChange as ReturnType<typeof vi.fn>;
    elementByLabel(root, 'Move stop-loss').props.onPointerDown?.(pointerEvent(10, 190));
    withPointerWindow((listeners) => {
      renderPreview(props);
      const cleanup = installDragEffect();
      listeners.get('pointermove')?.({ pointerId: 10, clientY: 200 } as unknown as Event);
      cleanup();
    });
    expect(stopChange).toHaveBeenLastCalledWith(99.8);
    expect(entryChange).not.toHaveBeenCalled();
  });

  it('places short protection geometry on the reversed sides of entry', () => {
    const bracket = createDefaultBacktestBracket({
      entryPrice: 100,
      direction: 'short',
      instrument: {
        pipSize: 0.01,
        pricePrecision: 2,
        contractSize: 100_000,
        quoteCurrency: 'USD',
        quoteToUsdRate: null,
      },
      account: { currentBalanceUsd: 10_000, riskPercent: 1 },
    });
    expect(bracket.stopLossPrice).toBeGreaterThan(bracket.entryPrice!);
    expect(bracket.takeProfitPrice).toBeLessThan(bracket.entryPrice!);

    const root = renderPreview(makePreviewProps({
      entryType: 'market',
      direction: 'short',
      entryPrice: 100,
      stopLossPrice: 100.1,
      takeProfitPrice: 99.9,
    }));
    const stop = elementByClass(root, 'backtest-bracket-preview-level--stop');
    const entry = elementByClass(root, 'backtest-bracket-preview-level--entry');
    const target = elementByClass(root, 'backtest-bracket-preview-level--target');

    expect(stop.props.style?.top as number).toBeLessThan(entry.props.style?.top as number);
    expect(target.props.style?.top as number).toBeGreaterThan(entry.props.style?.top as number);
  });

  it('disables Submit until the parent confirms valid prices and sizing', () => {
    const root = renderPreview(makePreviewProps({ canPlaceOrder: false }));
    const placeButton = elementByClass(root, 'backtest-bracket-preview-submit');

    expect(placeButton?.props.disabled).toBe(true);
  });

  it('shows submitting state and blocks both actions while an order is pending', () => {
    const root = renderPreview(makePreviewProps({ orderPending: true }));

    expect(elementByClass(root, 'backtest-bracket-preview-submit')).toMatchObject({ props: { disabled: true, children: 'Submitting…' } });
    expect(elementByClass(root, 'backtest-bracket-preview-cancel').props.disabled).toBe(true);
  });
});
