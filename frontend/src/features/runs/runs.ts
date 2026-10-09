import type { Run, RunEvent } from '../../api/client'
import type { Level } from '../signals/signals'

/** One line of a run's timeline, built from one or more log events. */
export type TimelineRow =
  | {
      kind: 'step'
      key: string
      label: string
      state: 'running' | 'done' | 'failed'
      /** What the step produced, or why it failed. */
      detail: string | null
      durationMs: number | null
    }
  | { kind: 'signal'; key: string; districtId: string; hazard: string; level: Level }
  | { kind: 'note'; key: string; text: string; failed: boolean }

const STEP_LABELS: Record<string, string> = {
  fetch_forecasts: 'Fetch forecasts',
  screen_weather: 'Screen weather',
  fetch_air_quality: 'Fetch air quality',
  screen_air_quality: 'Screen air quality',
  apply_alert_lifecycle: 'Update alerts',
}

export const RUN_STATUS_LABELS: Record<Run['status'], string> = {
  running: 'Running',
  succeeded: 'Succeeded',
  failed: 'Failed',
}

export function stepLabel(step: string): string {
  // An unknown step still reads sensibly: "draft_alerts" -> "Draft alerts"
  const fallback = step.replaceAll('_', ' ')
  return STEP_LABELS[step] ?? fallback.charAt(0).toUpperCase() + fallback.slice(1)
}

function count(value: unknown, singular: string): string | null {
  return typeof value === 'number' ? `${value} ${singular}${value === 1 ? '' : 's'}` : null
}

/** What a finished step produced, from the payload of its closing event. */
function stepOutcome(payload: RunEvent['payload']): string | null {
  const actions =
    payload.actions && typeof payload.actions === 'object'
      ? Object.entries(payload.actions)
          .map(([action, total]) => `${total} ${action}`)
          .join(', ') || 'no changes'
      : null
  return count(payload.snapshots, 'snapshot') ?? count(payload.signals, 'signal') ?? actions
}

/**
 * Fold a run's event log into timeline rows: a step's start and end become one
 * row, and the events that only repeat what a step row already says are dropped.
 */
export function buildTimeline(events: RunEvent[]): TimelineRow[] {
  const rows: TimelineRow[] = []
  const started = new Map<string, { index: number; at: number }>()

  for (const event of events) {
    const { payload } = event
    const key = String(event.seq)
    const step = String(payload.step)

    if (event.type === 'run_started') {
      rows.push({ kind: 'note', key, text: `Started (${String(payload.trigger)})`, failed: false })
    } else if (event.type === 'step_started') {
      started.set(step, { index: rows.length, at: Date.parse(event.at) })
      rows.push({ kind: 'step', key, label: stepLabel(step), state: 'running', detail: null, durationMs: null })
    } else if (event.type === 'step_finished' || event.type === 'step_failed') {
      const open = started.get(step)
      if (!open) continue
      const failed = event.type === 'step_failed'
      rows[open.index] = {
        kind: 'step',
        key: rows[open.index].key,
        label: stepLabel(step),
        state: failed ? 'failed' : 'done',
        detail: failed ? String(payload.error) : stepOutcome(payload),
        durationMs: Date.parse(event.at) - open.at,
      }
    } else if (event.type === 'signal_raised') {
      rows.push({
        kind: 'signal',
        key,
        districtId: String(payload.district_id),
        hazard: String(payload.hazard),
        level: payload.level as Level,
      })
    } else if (event.type === 'error') {
      rows.push({ kind: 'note', key, text: String(payload.message), failed: true })
    } else if (event.type === 'run_finished') {
      const failed = payload.status === 'failed'
      const totals = [count(payload.district_count, 'district'), count(payload.signal_count, 'signal')]
      rows.push({
        kind: 'note',
        key,
        text: failed ? 'Failed' : `Succeeded: ${totals.filter(Boolean).join(', ')}`,
        failed,
      })
    }
  }
  return rows
}

export function formatDuration(milliseconds: number): string {
  if (milliseconds < 1000) return `${Math.max(0, Math.round(milliseconds))} ms`
  const seconds = milliseconds / 1000
  if (seconds < 60) return `${seconds.toFixed(1)} s`
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`
}

/** How long a run took, or null while it is still running. */
export function runDuration(run: Run): string | null {
  if (!run.finished_at) return null
  return formatDuration(Date.parse(run.finished_at) - Date.parse(run.started_at))
}
