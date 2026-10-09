import type { RunEvent } from '../../api/client'
import { LEVEL_COLOURS, LEVEL_LABELS, hazardLabel } from '../signals/signals'
import type { StreamState } from './queries'
import { buildTimeline, formatDuration, type TimelineRow } from './runs'

const STATE_MARKS = { running: '…', done: '✓', failed: '✕' } as const
const STATE_NAMES = { running: 'In progress', done: 'Done', failed: 'Failed' } as const

function Row({ row, districtNames }: { row: TimelineRow; districtNames: Map<string, string> }) {
  if (row.kind === 'signal') {
    return (
      <li className="ml-5 border-l-[3px] pl-2 text-xs" style={{ borderColor: LEVEL_COLOURS[row.level] }}>
        <span className="type-label" style={{ color: LEVEL_COLOURS[row.level] }}>
          {LEVEL_LABELS[row.level]}
        </span>{' '}
        <span className="text-ink">
          {hazardLabel(row.hazard)} · {districtNames.get(row.districtId) ?? row.districtId}
        </span>
      </li>
    )
  }

  if (row.kind === 'note') {
    return (
      <li className={`text-xs ${row.failed ? 'font-semibold text-ink' : 'text-ink/70'}`}>
        {row.failed && <span className="type-label mr-1.5">Error</span>}
        <span className="break-words">{row.text}</span>
      </li>
    )
  }

  return (
    <li className="text-sm">
      <div className="flex items-baseline gap-2">
        <span className="w-3 shrink-0 font-mono text-xs text-ink/60" aria-hidden="true">
          {STATE_MARKS[row.state]}
        </span>
        <span className={row.state === 'failed' ? 'font-semibold text-ink' : 'text-ink'}>
          {row.label}
        </span>
        <span className="sr-only">{STATE_NAMES[row.state]}</span>
        {row.durationMs !== null && (
          <span className="ml-auto shrink-0 font-mono text-[0.6875rem] text-ink/55">
            {formatDuration(row.durationMs)}
          </span>
        )}
      </div>
      {row.detail && <p className="ml-5 break-words text-xs text-ink/70">{row.detail}</p>}
    </li>
  )
}

type Props = {
  events: RunEvent[]
  state: StreamState
  /** District id to display name, for the signals a run raised. */
  districtNames: Map<string, string>
}

/** The steps of one run in order, growing while the run is in progress. */
export function RunTimeline({ events, state, districtNames }: Props) {
  const rows = buildTimeline(events)

  return (
    <div>
      <p role="status" className="type-label text-ink/55">
        {state === 'connecting' && 'Loading timeline…'}
        {state === 'live' && 'Live'}
        {state === 'interrupted' && 'Connection lost. Reconnecting…'}
        {state === 'ended' && rows.length === 0 && 'No events were recorded for this run.'}
      </p>
      <ol className="mt-2 space-y-2" aria-label="Run timeline">
        {rows.map((row) => (
          <Row key={row.key} row={row} districtNames={districtNames} />
        ))}
      </ol>
    </div>
  )
}
