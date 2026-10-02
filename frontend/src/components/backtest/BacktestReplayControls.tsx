import { useMemo } from 'react';
import { ReplayControls, type ReplayController } from '@getcandlekit/charts/react';
import { createBacktestTimeFormatters } from '../../utils/backtestTimeFormat';

interface BacktestReplayControlsProps {
  controller: ReplayController;
  displayTimezone: string;
  blindMode: boolean;
}

/** Keep CandleKit's transport and seek controls, restricting speed choices to the product rates. */
export function BacktestReplayControls({
  controller,
  displayTimezone,
  blindMode,
}: BacktestReplayControlsProps) {
  const formatTime = useMemo(() => {
    const formatter = createBacktestTimeFormatters(displayTimezone, blindMode);
    return (timeMs: number) => formatter.timeFormatter(timeMs / 1_000);
  }, [blindMode, displayTimezone]);
  return (
    <div className="backtest-replay-controls">
      <ReplayControls
        controller={controller}
        speeds={[1, 2, 5, 15, 30]}
        formatTime={formatTime}
        showProgress
        className="ck-replay backtest-candlekit-replay"
      />
    </div>
  );
}
