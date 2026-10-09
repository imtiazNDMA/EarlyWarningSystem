import type { District, Run } from '../../api/client'
import { RunTimeline } from './RunTimeline'
import { useRunEvents, useRuns } from './queries'
import { RUN_STATUS_LABELS, runDuration } from './runs'

const STARTED = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

function RunSummary({ run }: { run: Run }) {
  const duration = runDuration(run)
  return (
    <>
      <span className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-ink">
          Run {run.id} · {RUN_STATUS_LABELS[run.status]}
        </span>
        <span className="font-mono text-[0.6875rem] text-ink/55">
          {STARTED.format(new Date(run.started_at))}
        </span>
      </span>
      <span className="block font-mono text-[0.6875rem] text-ink/55">
        {run.trigger}
        {duration && ` · ${duration}`}
        {run.status === 'succeeded' && ` · ${run.signal_count} signals`}
      </span>
    </>
  )
}

type ListProps = {
  runs: Run[]
  selectedRunId: number | null
  onSelect: (runId: number) => void
}

export function RunList({ runs, selectedRunId, onSelect }: ListProps) {
  if (runs.length === 0) {
    return <p className="text-sm text-ink/70">No monitoring cycle has run yet.</p>
  }

  return (
    <ul className="space-y-1">
      {runs.map((run) => (
        <li key={run.id}>
          <button
            type="button"
            aria-pressed={run.id === selectedRunId}
            onClick={() => onSelect(run.id)}
            className={`w-full rounded-sm px-2 py-1.5 text-left hover:bg-wash/70 ${run.id === selectedRunId ? 'bg-wash' : ''}`}
          >
            <RunSummary run={run} />
          </button>
        </li>
      ))}
    </ul>
  )
}

function SelectedRun({ runId, districtNames }: { runId: number; districtNames: Map<string, string> }) {
  const { events, state } = useRunEvents(runId)
  return <RunTimeline events={events} state={state} districtNames={districtNames} />
}

type Props = {
  districts: District[]
  selectedRunId: number | null
  onSelect: (runId: number) => void
  onClose: () => void
}

/** Monitoring cycles and, for the selected one, a timeline of what it did. */
export function RunsPanel({ districts, selectedRunId, onSelect, onClose }: Props) {
  const runs = useRuns()
  const districtNames = new Map(districts.map((district) => [district.id, district.name_en]))
  // With nothing chosen, follow the newest run
  const shownRunId = selectedRunId ?? runs.data?.[0]?.id ?? null

  return (
    <aside
      className="plate max-h-[60dvh] overflow-y-auto md:max-h-[calc(100dvh-1.5rem)]"
      aria-label="Monitoring runs"
    >
      <div className="flex items-start justify-between gap-3">
        <h2 className="type-display text-xl leading-tight text-ink">Monitoring runs</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close monitoring runs"
          className="-mr-1 -mt-1 grid size-8 shrink-0 place-items-center rounded-sm text-ink/60 hover:bg-wash hover:text-ink"
        >
          <svg viewBox="0 0 16 16" className="size-3.5" aria-hidden="true">
            <path d="M2 2l12 12M14 2L2 14" stroke="currentColor" strokeWidth="1.75" fill="none" />
          </svg>
        </button>
      </div>

      <div className="mt-3 max-h-44 overflow-y-auto border-t border-line/30 pt-3">
        {runs.isPending && (
          <p role="status" className="text-sm text-ink/70">
            Loading runs…
          </p>
        )}
        {runs.isError && (
          <div role="alert">
            <p className="text-sm text-ink">Monitoring runs could not be loaded.</p>
            <button
              type="button"
              onClick={() => runs.refetch()}
              className="mt-2 rounded-sm bg-signal px-3 py-1.5 text-sm font-semibold text-white hover:bg-ink"
            >
              Load runs again
            </button>
          </div>
        )}
        {runs.data && <RunList runs={runs.data} selectedRunId={shownRunId} onSelect={onSelect} />}
      </div>

      {shownRunId !== null && (
        <div className="mt-3 border-t border-line/30 pt-3">
          <h3 className="type-label mb-2 text-ink/60">Run {shownRunId}</h3>
          {/* Keyed so each run opens its own stream */}
          <SelectedRun key={shownRunId} runId={shownRunId} districtNames={districtNames} />
        </div>
      )}
    </aside>
  )
}
