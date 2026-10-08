import type { Signal } from '../../api/client'
import { hazardLabel, LEVEL_COLOURS, LEVEL_LABELS } from './signals'

const DAY_MONTH = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' })

function dayMonth(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  return DAY_MONTH.format(new Date(year, month - 1, day))
}

function period(signal: Signal): string {
  return signal.onset === signal.expires
    ? dayMonth(signal.onset)
    : `${dayMonth(signal.onset)} to ${dayMonth(signal.expires)}`
}

type Props = {
  /** Signals for one district, most severe first. */
  signals: Signal[]
  cycleHasRun: boolean
}

/** The hazard thresholds a district's forecast reached, and what triggered each. */
export function SignalList({ signals, cycleHasRun }: Props) {
  if (signals.length === 0) {
    return (
      <p className="text-sm text-ink/70">
        {cycleHasRun
          ? 'No hazard thresholds reached in the latest cycle.'
          : 'No monitoring cycle has run yet.'}
      </p>
    )
  }

  return (
    <ul className="space-y-3">
      {signals.map((signal) => (
        <li key={signal.hazard} className="flex gap-2.5">
          <span
            aria-hidden="true"
            className="mt-1 size-3 shrink-0 rounded-[2px] border border-ink/25"
            style={{ background: LEVEL_COLOURS[signal.level] }}
          />
          <div className="min-w-0 text-sm text-ink">
            <p>
              <span className="font-semibold">{LEVEL_LABELS[signal.level]}</span>
              <span className="text-ink/50"> · </span>
              <span>{hazardLabel(signal.hazard)}</span>
            </p>
            <p className="font-mono text-xs text-ink/70">{period(signal)}</p>
            <p className="mt-0.5 text-xs text-ink/70">
              Peak {signal.peak_value} {signal.unit} on {dayMonth(signal.peak_date)}.{' '}
              {LEVEL_LABELS[signal.level]} starts at {signal.threshold} {signal.unit}.
            </p>
          </div>
        </li>
      ))}
    </ul>
  )
}
