import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AirQualityView } from './AirQualityView'

describe('AirQualityView', () => {
  it('shows the PM2.5 value, unit, and forecast date', () => {
    render(
      <AirQualityView
        value={{
          district_id: 'lahore',
          date: '2026-10-08',
          pm2_5_mean_ug_m3: 72.35,
          fetched_at: '2026-10-08T09:00:00Z',
        }}
      />,
    )

    expect(screen.getByText('72.3')).toBeInTheDocument()
    expect(screen.getByText('µg/m³ daily mean PM2.5')).toBeInTheDocument()
    expect(screen.getByText('Forecast for 2026-10-08')).toBeInTheDocument()
  })

  it('shows an explicit no-data state', () => {
    render(<AirQualityView value={undefined} />)
    expect(screen.getByText('No air-quality forecast available.')).toBeInTheDocument()
  })
})
