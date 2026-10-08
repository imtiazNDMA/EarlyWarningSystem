import type { Run } from '../../api/client'
import { LEVEL_COLOURS, LEVEL_LABELS, LEVELS } from './signals'

const FINISHED = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

type Props = {
  /** The latest successful monitoring cycle, or null when none has run. */
  run: Run | null
  flaggedDistricts: number
}

/** Key to the map's severity colours, with the state of the latest cycle. */
export function SignalLegend({ run, flaggedDistricts }: Props) {
  return (
    <div className="mt-3 border-t border-line/30 pt-3">
      <p className="type-label text-ink/60">Highest hazard signal</p>
      <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink">
        {LEVELS.map((level) => (
          <li key={level} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-3 rounded-[2px] border border-ink/25"
              style={{ background: LEVEL_COLOURS[level] }}
            />
            {LEVEL_LABELS[level]}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-ink/60">
        {run?.finished_at
          ? `${flaggedDistricts} of ${run.district_count} districts flagged in the cycle of ${FINISHED.format(new Date(run.finished_at))}.`
          : 'No monitoring cycle has run yet.'}
      </p>
    </div>
  )
}
