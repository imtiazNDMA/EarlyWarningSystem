import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Alert, Run, RunEvent } from '../../api/client'
import { AlertList } from '../alerts/AlertList'
import { RunList } from './RunsPanel'
import { RunTimeline } from './RunTimeline'
import { useRunEvents } from './queries'
import { buildTimeline, formatDuration, runDuration, stepLabel } from './runs'

let seq = 0

function event(type: RunEvent['type'], payload: RunEvent['payload'] = {}, second = 0): RunEvent {
  seq += 1
  return { seq, type, payload, at: `2026-10-09T06:00:${String(second).padStart(2, '0')}Z` }
}

function run(overrides: Partial<Run> = {}): Run {
  return {
    id: 7,
    trigger: 'manual',
    status: 'succeeded',
    started_at: '2026-10-09T06:00:00Z',
    finished_at: '2026-10-09T06:00:12Z',
    district_count: 155,
    signal_count: 1,
    error: null,
    ...overrides,
  }
}

beforeEach(() => {
  seq = 0
})

describe('buildTimeline', () => {
  it('folds the start and end of a step into one finished row', () => {
    const rows = buildTimeline([
      event('step_started', { step: 'fetch_forecasts' }, 1),
      event('source_fetched', { source: 'open-meteo-forecast', snapshots: 155 }, 3),
      event('step_finished', { step: 'fetch_forecasts', snapshots: 155 }, 3),
    ])

    expect(rows).toEqual([
      {
        kind: 'step',
        key: '1',
        label: 'Fetch forecasts',
        state: 'done',
        detail: '155 snapshots',
        durationMs: 2000,
      },
    ])
  })

  it('leaves a step that has not ended as running', () => {
    const [row] = buildTimeline([event('step_started', { step: 'screen_weather' })])

    expect(row).toMatchObject({ kind: 'step', state: 'running', detail: null, durationMs: null })
  })

  it('shows why a step failed', () => {
    const [row] = buildTimeline([
      event('step_started', { step: 'fetch_air_quality' }),
      event('step_failed', { step: 'fetch_air_quality', error: 'HTTP 503: unavailable' }),
    ])

    expect(row).toMatchObject({ label: 'Fetch air quality', state: 'failed', detail: 'HTTP 503: unavailable' })
  })

  it('lists signals under the step that raised them', () => {
    const rows = buildTimeline([
      event('step_started', { step: 'screen_weather' }),
      event('signal_raised', { district_id: 'lahore', hazard: 'heavy_rain', level: 'severe' }),
      event('step_finished', { step: 'screen_weather', signals: 1 }),
    ])

    expect(rows.map((row) => row.kind)).toEqual(['step', 'signal'])
    expect(rows[0]).toMatchObject({ detail: '1 signal' })
    expect(rows[1]).toMatchObject({ districtId: 'lahore', hazard: 'heavy_rain', level: 'severe' })
  })

  it('summarises alert changes and how the run ended', () => {
    const rows = buildTimeline([
      event('run_started', { trigger: 'manual' }),
      event('step_started', { step: 'apply_alert_lifecycle' }),
      event('step_finished', { step: 'apply_alert_lifecycle', actions: { issue: 1, keep: 3 } }),
      event('run_finished', { status: 'succeeded', district_count: 155, signal_count: 1 }),
    ])

    expect(rows[0]).toMatchObject({ kind: 'note', text: 'Started (manual)' })
    expect(rows[1]).toMatchObject({ label: 'Update alerts', detail: '1 issue, 3 keep' })
    expect(rows[2]).toMatchObject({ text: 'Succeeded: 155 districts, 1 signal', failed: false })
  })

  it('follows an analysis from its tool calls to the assessment', () => {
    const subject = { district_id: 'lahore', hazard: 'heavy_rain' }
    const rows = buildTimeline([
      event('analysis_started', { ...subject, level: 'severe' }),
      event('tool_called', { ...subject, tool: 'get_forecast', arguments: { days: 2 } }),
      event('tool_result', { ...subject, tool: 'get_forecast', ok: true, result: '[]' }),
      event('tool_called', { ...subject, tool: 'get_river_level', arguments: {} }),
      event('tool_result', { ...subject, tool: 'get_river_level', ok: false, result: 'Unknown tool' }),
      event('assessment', {
        ...subject,
        decision: 'upgrade',
        severity: 'extreme',
        reasoning: 'Rain falls on saturated ground.',
      }),
    ])

    expect(rows).toMatchObject([
      {
        kind: 'analysis',
        state: 'done',
        decision: 'upgrade',
        level: 'extreme',
        detail: 'Rain falls on saturated ground.',
      },
      { kind: 'tool', tool: 'get_forecast', ok: true },
      { kind: 'tool', tool: 'get_river_level', ok: false },
    ])
  })

  it('says why an analysis ended without an assessment, and what was skipped', () => {
    const subject = { district_id: 'lahore', hazard: 'heavy_rain' }
    const rows = buildTimeline([
      event('analysis_skipped', { reason: 'over the per-run limit', signals: 2 }),
      event('analysis_started', { ...subject, level: 'severe' }),
      event('analysis_failed', { ...subject, reason: 'step_limit' }),
    ])

    expect(rows).toMatchObject([
      { kind: 'note', text: 'Analysis skipped for 2 signals: over the per-run limit' },
      {
        kind: 'analysis',
        state: 'failed',
        decision: null,
        level: 'severe',
        detail: 'Stopped at the step limit; the rule-based alert stands',
      },
    ])
  })

  it('marks the error and the ending of a failed run', () => {
    const rows = buildTimeline([
      event('error', { message: 'open-meteo-forecast: HTTP 503' }),
      event('run_finished', { status: 'failed', district_count: 0, signal_count: 0 }),
    ])

    expect(rows).toMatchObject([
      { text: 'open-meteo-forecast: HTTP 503', failed: true },
      { text: 'Failed', failed: true },
    ])
  })
})

describe('run formatting', () => {
  it('names unknown steps from their identifier', () => {
    expect(stepLabel('draft_alerts')).toBe('Draft alerts')
  })

  it('formats durations at the scale they happen', () => {
    expect(formatDuration(240)).toBe('240 ms')
    expect(formatDuration(12_340)).toBe('12.3 s')
    expect(formatDuration(125_000)).toBe('2 min 5 s')
  })

  it('has no duration for a run still in progress', () => {
    expect(runDuration(run())).toBe('12.0 s')
    expect(runDuration(run({ status: 'running', finished_at: null }))).toBeNull()
  })
})

describe('RunTimeline', () => {
  it('shows steps, signals with district names, and the live state', () => {
    render(
      <RunTimeline
        state="live"
        districtNames={new Map([['lahore', 'Lahore']])}
        events={[
          event('step_started', { step: 'screen_weather' }),
          event('signal_raised', { district_id: 'lahore', hazard: 'heavy_rain', level: 'severe' }),
        ]}
      />,
    )

    const timeline = screen.getByRole('list', { name: 'Run timeline' })
    expect(within(timeline).getByText('Screen weather')).toBeInTheDocument()
    expect(within(timeline).getByText('In progress')).toBeInTheDocument()
    expect(within(timeline).getByText('Heavy rain · Lahore')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Live')
  })

  it('shows what the analyst decided and why', () => {
    const subject = { district_id: 'lahore', hazard: 'heavy_rain' }
    render(
      <RunTimeline
        state="ended"
        districtNames={new Map([['lahore', 'Lahore']])}
        events={[
          event('analysis_started', { ...subject, level: 'severe' }),
          event('tool_called', { ...subject, tool: 'get_forecast', arguments: {} }),
          event('assessment', {
            ...subject,
            decision: 'downgrade',
            severity: 'moderate',
            reasoning: 'The peak is brief and neighbours are dry.',
          }),
        ]}
      />,
    )

    expect(screen.getByText('Downgraded')).toBeInTheDocument()
    expect(screen.getByText('Moderate')).toBeInTheDocument()
    expect(screen.getByText('The peak is brief and neighbours are dry.')).toBeInTheDocument()
    expect(screen.getByText('get_forecast')).toBeInTheDocument()
  })

  it('says so when a finished run recorded nothing', () => {
    render(<RunTimeline state="ended" districtNames={new Map()} events={[]} />)

    expect(screen.getByRole('status')).toHaveTextContent('No events were recorded for this run.')
  })
})

describe('RunList', () => {
  it('lists runs with their status and selects one', async () => {
    const onSelect = vi.fn()
    render(
      <RunList
        runs={[run({ id: 8, status: 'failed' }), run()]}
        selectedRunId={7}
        onSelect={onSelect}
      />,
    )

    expect(screen.getByRole('button', { name: /Run 7 · Succeeded/ })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: /Run 8 · Failed/ }))

    expect(onSelect).toHaveBeenCalledWith(8)
  })

  it('has an explicit empty state', () => {
    render(<RunList runs={[]} selectedRunId={null} onSelect={vi.fn()} />)

    expect(screen.getByText('No monitoring cycle has run yet.')).toBeInTheDocument()
  })
})

describe('alert link to its run', () => {
  it('opens the run that produced the alert', async () => {
    const onOpenRun = vi.fn()
    const alert: Alert = {
      id: 1,
      district_id: 'lahore',
      district_name: 'Lahore',
      province: 'Punjab',
      hazard: 'heavy_rain',
      severity: 'severe',
      urgency: 'expected',
      certainty: 'likely',
      onset: '2026-10-09',
      expires: '2026-10-10',
      headline_en: 'Severe heavy rain alert for Lahore',
      body_en: 'Heavy rain peaks at 120 mm on 9 October.',
      instructions_en: 'Avoid low-lying areas.',
      headline_ur: null,
      body_ur: null,
      instructions_ur: null,
      generated_by: 'rules',
      evidence: [],
      status: 'active',
      issued_at: '2026-10-08T09:00:00Z',
      ended_at: null,
      supersedes_id: null,
      run_id: 7,
    }
    render(<AlertList alerts={[alert]} onOpenRun={onOpenRun} />)

    await userEvent.click(screen.getByRole('button', { name: 'Run 7' }))

    expect(onOpenRun).toHaveBeenCalledWith(7)
  })
})

/** Stand-in for the browser's EventSource, driven by the test. */
class FakeEventSource {
  static CLOSED = 2
  static latest: FakeEventSource
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((message: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  readonly url: string
  private listeners = new Map<string, () => void>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.latest = this
  }

  addEventListener(type: string, listener: () => void) {
    this.listeners.set(type, listener)
  }

  close() {
    this.readyState = FakeEventSource.CLOSED
  }

  send(event: RunEvent) {
    this.onmessage?.({ data: JSON.stringify(event) })
  }

  end() {
    this.listeners.get('end')?.()
  }
}

function Probe({ runId }: { runId: number }) {
  const { events, state } = useRunEvents(runId)
  return (
    <p>
      {state}: {events.map((item) => item.type).join(',')}
    </p>
  )
}

describe('useRunEvents', () => {
  beforeEach(() => {
    vi.stubGlobal('EventSource', FakeEventSource)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('adds events as they arrive and stops when the server ends the stream', () => {
    render(<Probe runId={7} />)
    const source = FakeEventSource.latest
    expect(source.url).toBe('/api/runs/7/events')
    expect(screen.getByText('connecting:')).toBeInTheDocument()

    const started = event('run_started', { trigger: 'manual' })
    act(() => {
      source.onopen?.()
      source.send(started)
      source.send(started)
      source.send(event('run_finished', { status: 'succeeded' }))
    })
    expect(screen.getByText('live: run_started,run_finished')).toBeInTheDocument()

    act(() => source.end())
    expect(screen.getByText('ended: run_started,run_finished')).toBeInTheDocument()
    expect(source.readyState).toBe(FakeEventSource.CLOSED)
  })

  it('reports a dropped connection while the browser reconnects', () => {
    render(<Probe runId={7} />)

    act(() => FakeEventSource.latest.onerror?.())

    expect(screen.getByText('interrupted:')).toBeInTheDocument()
  })

  it('closes the stream when the run is no longer shown', () => {
    const { unmount } = render(<Probe runId={7} />)

    unmount()

    expect(FakeEventSource.latest.readyState).toBe(FakeEventSource.CLOSED)
  })
})
