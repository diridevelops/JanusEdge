import { ReplayControls, type ReplayController } from '@getcandlekit/charts/react';

interface BacktestReplayControlsProps {
  controller: ReplayController;
  displayTimezone: string;
}

function createTimeFormatter(timezone: string) {
  return (timeMs: number) => {
    try {
      return new Intl.DateTimeFormat(undefined, {
        timeZone: timezone || 'UTC',
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hourCycle: 'h23',
        timeZoneName: 'short',
      }).format(new Date(timeMs));
    } catch {
      return new Date(timeMs).toISOString();
    }
  };
}

/** Keep CandleKit's transport and seek controls, restricting speed choices to the product rates. */
export function BacktestReplayControls({
  controller,
  displayTimezone,
}: BacktestReplayControlsProps) {
  return (
    <div className="backtest-replay-controls">
      <ReplayControls
        controller={controller}
        speeds={[1, 5, 20]}
        formatTime={createTimeFormatter(displayTimezone)}
        showProgress
        className="ck-replay backtest-candlekit-replay"
      />
    </div>
  );
}
