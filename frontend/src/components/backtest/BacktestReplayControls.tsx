import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Pause, Play, SkipForward } from 'lucide-react';
import { ReplayControls, type ReplayController, type ReplayState } from '@getcandlekit/charts/react';
import { createBacktestTimeFormatters } from '../../utils/backtestTimeFormat';

interface BacktestReplayControlsProps {
  controller: ReplayController;
  displayTimezone: string;
  blindMode: boolean;
  latestTimeMs: number | null;
  isAtLatest: boolean;
  navigationDisabled?: boolean;
}

/** Keep CandleKit's replay clock and seek bar with a compact app-specific transport. */
export function BacktestReplayControls({
  controller,
  displayTimezone,
  blindMode,
  latestTimeMs,
  isAtLatest,
  navigationDisabled = false,
}: BacktestReplayControlsProps) {
  const [replayState, setReplayState] = useState<ReplayState>(() => controller.getState());
  useEffect(() => controller.subscribe(setReplayState), [controller]);
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        event.defaultPrevented
        || event.repeat
        || event.altKey
        || event.ctrlKey
        || event.metaKey
        || event.shiftKey
        || navigationDisabled
      ) return;

      const target = event.target instanceof HTMLElement ? event.target : null;
      if (
        target?.isContentEditable
        || target?.closest('input, textarea, select, [contenteditable], [role="textbox"], [role="combobox"], [role="slider"], [role="spinbutton"]')
      ) return;

      const state = controller.getState();
      if (state.status !== 'ready') return;

      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        controller.step(-1);
      } else if (event.key === 'ArrowRight') {
        event.preventDefault();
        controller.step(1);
      } else if (event.code === 'Space' || event.key === ' ') {
        if (target?.closest('button, [role="button"], a[href]')) return;
        event.preventDefault();
        if (state.playing) controller.pause();
        else controller.play();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [controller, navigationDisabled]);

  const formatTime = useMemo(() => {
    const formatter = createBacktestTimeFormatters(displayTimezone, blindMode);
    return (timeMs: number) => formatter.timeFormatter(timeMs / 1_000);
  }, [blindMode, displayTimezone]);
  const isReady = replayState.status === 'ready';
  const isPlaying = isReady && replayState.playing;
  const speed = isReady ? replayState.speed : 1;
  const transportDisabled = !isReady || navigationDisabled;

  return (
    <div className="backtest-replay-controls">
      <ReplayControls
        controller={controller}
        speeds={[1, 2, 5, 15, 30]}
        formatTime={formatTime}
        showProgress
        className="ck-replay backtest-candlekit-replay"
      />
      <div className="backtest-replay-transport" role="group" aria-label="Replay controls">
        <button
          type="button"
          className="backtest-replay-segment"
          aria-label="Step back one candle"
          aria-keyshortcuts="ArrowLeft"
          title="Step back one candle (Left Arrow)"
          disabled={transportDisabled}
          onClick={() => controller.step(-1)}
        >
          <ChevronLeft aria-hidden="true" />
        </button>
        <button
          type="button"
          className="backtest-replay-segment backtest-replay-play"
          aria-label={isPlaying ? 'Pause replay' : 'Play replay'}
          aria-keyshortcuts="Space"
          title={isPlaying ? 'Pause replay (Spacebar)' : 'Play replay (Spacebar)'}
          aria-pressed={isPlaying}
          disabled={transportDisabled}
          onClick={() => (isPlaying ? controller.pause() : controller.play())}
        >
          {isPlaying
            ? <Pause aria-hidden="true" />
            : <Play aria-hidden="true" />}
        </button>
        <button
          type="button"
          className="backtest-replay-segment"
          aria-label="Step forward one candle"
          aria-keyshortcuts="ArrowRight"
          title="Step forward one candle (Right Arrow)"
          disabled={transportDisabled}
          onClick={() => controller.step(1)}
        >
          <ChevronRight aria-hidden="true" />
        </button>
        <button
          type="button"
          className="backtest-replay-segment backtest-replay-return-latest"
          aria-label="Return to latest candle"
          title={isAtLatest ? 'Already at the last viewed candle' : 'Return to the last viewed candle'}
          disabled={transportDisabled || isAtLatest || latestTimeMs == null}
          onClick={() => {
            if (latestTimeMs != null) controller.seek(latestTimeMs);
          }}
        >
          <SkipForward aria-hidden="true" />
        </button>
        <select
          className="backtest-replay-speed"
          aria-label="Playback speed"
          title="Playback speed"
          value={speed}
          disabled={transportDisabled}
          onChange={(event) => controller.setSpeed(Number(event.target.value))}
        >
          {[1, 2, 5, 15, 30].map((value) => (
            <option key={value} value={value}>{value}×</option>
          ))}
        </select>
      </div>
    </div>
  );
}
