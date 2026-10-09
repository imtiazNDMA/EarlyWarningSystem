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
  | {
      kind: 'analysis'
      key: string
      districtId: string
      hazard: string
      state: 'running' | 'done' | 'failed'
      /** The severity the analyst settled on; the screening level until then. */
      level: Level
      decision: Decision | null
      /** The analyst's reasoning, or why the analysis ended without one. */
      detail: string | null
    }
  | { kind: 'tool'; key: string; tool: string; ok: boolean | null }
  | { kind: 'note'; key: string; text: string; failed: boolean }

export type Decision = 'confirm' | 'upgrade' | 'downgrade' | 'dismiss'

export const DECISION_LABELS: Record<Decision, string> = {
  confirm: 'Confirmed',
  upgrade: 'Upgraded',
  downgrade: 'Downgraded',
  dismiss: 'Dismissed',
}

const FAILURE_REASONS: Record<string, string> = {
  step_limit: 'Stopped at the step limit; the rule-based alert stands',
  time_budget: 'Ran out of time; the rule-based alert stands',
  model_error: 'The model failed; the rule-based alert stands',
}

const STEP_LABELS: Record<string, string> = {
  fetch_forecasts: 'Fetch forecasts',
  screen_weather: 'Screen weather',
  fetch_air_quality: 'Fetch air quality',
  screen_air_quality: 'Screen air quality',
  analyse_signals: 'Analyse signals',
  draft_alerts: 'Draft and verify alerts',
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
  const analysed = typeof payload.analysed === 'number' ? `${payload.analysed} analysed` : null
  const drafted =
    typeof payload.drafted === 'number'
      ? `${payload.drafted} drafted, ${Number(payload.held ?? 0)} held`
      : null
  return (
    count(payload.snapshots, 'snapshot') ?? count(payload.signals, 'signal') ?? analysed ?? drafted ?? actions
  )
}

/** The hazard and district an event concerns, in words. */
function subject(payload: RunEvent['payload']): string {
  return `${String(payload.hazard).replaceAll('_', ' ')} in ${String(payload.district_id)}`
}

/**
 * Fold a run's event log into timeline rows: a step's start and end become one
 * row, and the events that only repeat what a step row already says are dropped.
 */
export function buildTimeline(events: RunEvent[]): TimelineRow[] {
  const rows: TimelineRow[] = []
  const started = new Map<string, { index: number; at: number }>()
  // Where the open analysis and tool rows are, so later events can finish them
  const analyses = new Map<string, number>()
  const tools = new Map<string, number>()

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
    } else if (event.type === 'analysis_started') {
      analyses.set(`${payload.district_id}/${payload.hazard}`, rows.length)
      rows.push({
        kind: 'analysis',
        key,
        districtId: String(payload.district_id),
        hazard: String(payload.hazard),
        state: 'running',
        level: payload.level as Level,
        decision: null,
        detail: null,
      })
    } else if (event.type === 'assessment' || event.type === 'analysis_failed') {
      const index = analyses.get(`${payload.district_id}/${payload.hazard}`)
      const open = index === undefined ? undefined : rows[index]
      if (index === undefined || open?.kind !== 'analysis') continue
      rows[index] =
        event.type === 'assessment'
          ? {
              ...open,
              state: 'done',
              level: payload.severity as Level,
              decision: payload.decision as Decision,
              detail: String(payload.reasoning),
            }
          : {
              ...open,
              state: 'failed',
              detail: FAILURE_REASONS[String(payload.reason)] ?? String(payload.reason),
            }
    } else if (event.type === 'tool_called') {
      tools.set(String(payload.tool), rows.length)
      rows.push({ kind: 'tool', key, tool: String(payload.tool), ok: null })
    } else if (event.type === 'tool_result') {
      const index = tools.get(String(payload.tool))
      const open = index === undefined ? undefined : rows[index]
      if (index === undefined || open?.kind !== 'tool') continue
      rows[index] = { ...open, ok: payload.ok === true }
    } else if (event.type === 'analysis_skipped') {
      rows.push({
        kind: 'note',
        key,
        text: `Analysis skipped for ${count(payload.signals, 'signal') ?? 'some signals'}: ${String(payload.reason)}`,
        failed: false,
      })
    } else if (event.type === 'draft_checked') {
      const problems = Array.isArray(payload.problems) ? payload.problems.join(' ') : ''
      rows.push({
        kind: 'note',
        key,
        text: `Draft ${Number(payload.attempt)} for ${subject(payload)} ${payload.passed === true ? 'verified' : `rejected: ${problems}`}`,
        failed: false,
      })
    } else if (event.type === 'alert_held') {
      const reasons = Array.isArray(payload.reasons) ? payload.reasons.join(' ') : ''
      rows.push({
        kind: 'note',
        key,
        text: `Alert for ${subject(payload)} held, not published: ${reasons}`,
        failed: true,
      })
    } else if (event.type === 'draft_failed') {
      rows.push({
        kind: 'note',
        key,
        text: `No draft for ${subject(payload)}; rule-based wording used`,
        failed: false,
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
