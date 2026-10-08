import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { Run, Signal } from '../../api/client'
import { SignalLegend } from './SignalLegend'
import { SignalList } from './SignalList'
import { hazardLabel, highestLevel, signalsByDistrict, summarise } from './signals'

function signal(overrides: Partial<Signal> = {}): Signal {
  return {
    district_id: 'lahore',
    hazard: 'heavy_rain',
    level: 'severe',
    onset: '2026-10-09',
    expires: '2026-10-10',
    metric: 'precipitation_mm',
    unit: 'mm',
    peak_value: 120,
    peak_date: '2026-10-09',
    threshold: 100,
    days_over: ['2026-10-09', '2026-10-10'],
    snapshot_id: 1,
    ...overrides,
  }
}

const run: Run = {
  id: 7,
  trigger: 'manual',
  status: 'succeeded',
  started_at: '2026-10-08T09:00:00Z',
  finished_at: '2026-10-08T09:00:05Z',
  district_count: 155,
  signal_count: 2,
  error: null,
}

describe('highestLevel', () => {
  it('is null without signals', () => {
    expect(highestLevel([])).toBeNull()
  })

  it('picks the most severe level whatever the order', () => {
    const signals = [
      signal({ level: 'extreme' }),
      signal({ level: 'moderate' }),
      signal({ level: 'severe' }),
    ]

    expect(highestLevel(signals)).toBe('extreme')
  })
})

describe('signalsByDistrict', () => {
  it('groups by district with the most severe first', () => {
    const groups = signalsByDistrict([
      signal({ district_id: 'lahore', hazard: 'strong_wind', level: 'moderate' }),
      signal({ district_id: 'kasur', level: 'moderate' }),
      signal({ district_id: 'lahore', hazard: 'heavy_rain', level: 'extreme' }),
    ])

    expect(groups.get('lahore')?.map((s) => s.hazard)).toEqual(['heavy_rain', 'strong_wind'])
    expect(groups.get('kasur')).toHaveLength(1)
  })
})

describe('summarise', () => {
  it('names the hazards at the highest level only', () => {
    const signals = [
      signal({ hazard: 'heavy_rain', level: 'severe' }),
      signal({ hazard: 'strong_wind', level: 'severe' }),
      signal({ hazard: 'heatwave', level: 'moderate' }),
    ]

    expect(summarise(signals)).toBe('Severe: heavy rain, strong wind')
  })

  it('is null without signals', () => {
    expect(summarise([])).toBeNull()
  })
})

describe('hazardLabel', () => {
  it('makes an unknown hazard readable', () => {
    expect(hazardLabel('dust_storm')).toBe('Dust storm')
  })
})

describe('SignalList', () => {
  it('describes what triggered each signal', () => {
    render(<SignalList signals={[signal()]} cycleHasRun />)

    expect(screen.getByText('Severe')).toBeInTheDocument()
    expect(screen.getByText('Heavy rain')).toBeInTheDocument()
    expect(screen.getByText('9 Oct to 10 Oct')).toBeInTheDocument()
    expect(
      screen.getByText('Peak 120 mm on 9 Oct. Severe starts at 100 mm.'),
    ).toBeInTheDocument()
  })

  it('shows a single day without a range', () => {
    render(
      <SignalList
        signals={[signal({ onset: '2026-10-09', expires: '2026-10-09' })]}
        cycleHasRun
      />,
    )

    expect(screen.getByText('9 Oct')).toBeInTheDocument()
  })

  it('says when the latest cycle found nothing for the district', () => {
    render(<SignalList signals={[]} cycleHasRun />)

    expect(
      screen.getByText('No hazard thresholds reached in the latest cycle.'),
    ).toBeInTheDocument()
  })

  it('says when no cycle has run', () => {
    render(<SignalList signals={[]} cycleHasRun={false} />)

    expect(screen.getByText('No monitoring cycle has run yet.')).toBeInTheDocument()
  })
})

describe('SignalLegend', () => {
  it('names every level and reports the latest cycle', () => {
    render(<SignalLegend run={run} flaggedDistricts={2} />)

    expect(screen.getByText('Moderate')).toBeInTheDocument()
    expect(screen.getByText('Severe')).toBeInTheDocument()
    expect(screen.getByText('Extreme')).toBeInTheDocument()
    expect(screen.getByText(/2 of 155 districts flagged/)).toBeInTheDocument()
  })

  it('says when no cycle has run', () => {
    render(<SignalLegend run={null} flaggedDistricts={0} />)

    expect(screen.getByText('No monitoring cycle has run yet.')).toBeInTheDocument()
  })
})
