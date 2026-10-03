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
          title="Step back one candle"
          disabled={transportDisabled}
          onClick={() => controller.step(-1)}
        >
          <ChevronLeft aria-hidden="true" />
        </button>
        <button
          type="button"
          className="backtest-replay-segment backtest-replay-play"
          aria-label={isPlaying ? 'Pause replay' : 'Play replay'}
          title={isPlaying ? 'Pause replay' : 'Play replay'}
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
          title="Step forward one candle"
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
