import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { Alert, District } from '../../api/client'
import { AlertFeed } from './AlertFeed'
import { AlertList } from './AlertList'
import { alertsByDistrict, highestAlertLevel, summariseAlerts } from './alerts'

function alert(overrides: Partial<Alert> = {}): Alert {
  return {
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
    evidence: [
      {
        snapshot_id: 12,
        metric: 'precipitation_mm',
        unit: 'mm',
        date: '2026-10-09',
        value: 120,
        threshold: 100,
      },
    ],
    status: 'active',
    held_reasons: null,
    issued_at: '2026-10-08T09:00:00Z',
    ended_at: null,
    supersedes_id: null,
    run_id: 7,
    ...overrides,
  }
}

const lahore: District = {
  id: 'lahore',
  name_en: 'Lahore',
  name_ur: null,
  province: 'Punjab',
  lat: 31.4614,
  lon: 74.3552,
  feature_id: 'lahore',
}

describe('alert map helpers', () => {
  it('groups alerts by district with the most severe first', () => {
    const groups = alertsByDistrict([
      alert({ id: 1, severity: 'moderate' }),
      alert({ id: 2, severity: 'extreme' }),
      alert({ id: 3, district_id: 'kasur' }),
    ])

    expect(groups.get('lahore')?.map((item) => item.id)).toEqual([2, 1])
    expect(highestAlertLevel(groups.get('lahore') ?? [])).toBe('extreme')
  })

  it('summarises hazards at the highest alert level only', () => {
    expect(
      summariseAlerts([
        alert({ hazard: 'heavy_rain', severity: 'severe' }),
        alert({ id: 2, hazard: 'strong_wind', severity: 'severe' }),
        alert({ id: 3, hazard: 'heatwave', severity: 'moderate' }),
      ]),
    ).toBe('Severe: heavy rain, strong wind')
  })
})

describe('AlertList', () => {
  it('shows alert text, safety instructions, and evidence', () => {
    render(<AlertList alerts={[alert()]} />)

    expect(screen.getByRole('heading', { name: 'Severe heavy rain alert for Lahore' })).toBeInTheDocument()
    expect(screen.getByText('Safety:')).toBeInTheDocument()
    expect(screen.getByText('120 mm')).toBeInTheDocument()
    expect(screen.getByText('100 mm')).toBeInTheDocument()
    expect(screen.getByText(/Source snapshot 12/)).toBeInTheDocument()
  })

  it('has an explicit empty state', () => {
    render(<AlertList alerts={[]} />)

    expect(screen.getByText('No active alerts for this district.')).toBeInTheDocument()
  })
})

describe('held alerts', () => {
  it('shows in the feed that an alert was held and why', () => {
    render(
      <AlertFeed
        alerts={[
          alert({ status: 'held', held_reasons: ['The number 300 is not in the evidence.'] }),
        ]}
        districts={[lahore]}
        onSelect={vi.fn()}
      />,
    )

    expect(screen.getByText('Held: not published')).toBeInTheDocument()
    expect(screen.getByText('The number 300 is not in the evidence.')).toBeInTheDocument()
  })
})

describe('AlertFeed', () => {
  it('shows lifecycle status and opens the district selected from the feed', async () => {
    const onSelect = vi.fn()
    render(
      <AlertFeed
        alerts={[alert({ status: 'superseded' })]}
        districts={[lahore]}
        onSelect={onSelect}
      />,
    )

    expect(screen.getByText(/superseded/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Heavy rain · Lahore/ }))

    expect(onSelect).toHaveBeenCalledWith(lahore)
  })
})
