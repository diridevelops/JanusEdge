import { describe, expect, it } from 'vitest';
import { getExecutionMarkerStyle } from './executionMarkerStyle';

describe('getExecutionMarkerStyle', () => {
  it.each(['buy', 'Buy'] as const)('renders %s as a green upward buy marker', (side) => {
    expect(getExecutionMarkerStyle(side)).toEqual({
      position: 'belowBar',
      color: '#22c55e',
      shape: 'arrowUp',
      label: 'Buy',
    });
  });

  it.each(['sell', 'Sell'] as const)('renders %s as a red downward sell marker', (side) => {
    expect(getExecutionMarkerStyle(side)).toEqual({
      position: 'aboveBar',
      color: '#ef4444',
      shape: 'arrowDown',
      label: 'Sell',
    });
  });
});
