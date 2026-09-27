import { describe, expect, it, vi } from 'vitest';
import { CandleKitReplayFollowButton } from './CandleKitReplayChart';

describe('CandleKit replay follow control', () => {
  it('is hidden while the pane follows the latest candle', () => {
    expect(CandleKitReplayFollowButton({
      isFollowing: true,
      onSnapToLive: vi.fn(),
    })).toBeNull();
  });

  it('exposes an accessible snap action while the pane is away from the live edge', () => {
    const onSnapToLive = vi.fn();
    const button = CandleKitReplayFollowButton({
      isFollowing: false,
      onSnapToLive,
    });

    expect(button).not.toBeNull();
    if (!button) return;
    expect(button.type).toBe('button');
    expect(button.props['aria-label']).toBe('Snap chart to latest candle');
    button.props.onClick();
    expect(onSnapToLive).toHaveBeenCalledOnce();
  });
});
