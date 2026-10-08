import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { DailyForecast, Forecast } from '../../api/client'
import { ForecastView } from './ForecastView'

function day(date: string, overrides: Partial<DailyForecast> = {}): DailyForecast {
  return {
    date,
    temperature_max_c: 32,
    temperature_min_c: 23.1,
    precipitation_mm: 0,
    precipitation_probability_pct: 10,
    wind_speed_max_kmh: 9.9,
    wind_gusts_max_kmh: 22.3,
    weather_code: 0,
    snowfall_cm: 0,
    uv_index_max: 6.2,
    ...overrides,
  }
}

function forecast(days: DailyForecast[], overrides: Partial<Forecast> = {}): Forecast {
  return {
    district_id: 'lahore',
    source: 'open-meteo-forecast',
    fetched_at: '2026-10-08T09:00:00Z',
    stale: false,
    days,
    ...overrides,
  }
}

describe('ForecastView', () => {
  it('reads out the first day until another is pointed at', async () => {
    render(
      <ForecastView
        forecast={forecast([
          day('2026-10-08'),
          day('2026-10-09', {
            temperature_max_c: 28,
            temperature_min_c: 22.3,
            precipitation_mm: 12.4,
            precipitation_probability_pct: 80,
          }),
        ])}
      />,
    )

    const readout = screen.getByTestId('forecast-readout')
    expect(readout).toHaveTextContent('Thu 8 Oct')
    expect(readout).toHaveTextContent('32° / 23°')
    expect(readout).toHaveTextContent('0.0 mm')

    await userEvent.hover(screen.getByTestId('forecast-day-1'))

    expect(readout).toHaveTextContent('Fri 9 Oct')
    expect(readout).toHaveTextContent('28° / 22°')
    expect(readout).toHaveTextContent('12.4 mm')
    expect(readout).toHaveTextContent('80% chance')
  })

  it('offers the same values as a table', async () => {
    render(
      <ForecastView
        forecast={forecast([
          day('2026-10-08'),
          day('2026-10-09', { precipitation_mm: 12.4 }),
        ])}
      />,
    )

    await userEvent.click(screen.getByText('Show as a table'))

    const rows = within(screen.getByRole('table')).getAllByRole('row')
    expect(rows).toHaveLength(3)
    expect(rows[2]).toHaveTextContent('Fri 9 Oct')
    expect(rows[2]).toHaveTextContent('32')
    expect(rows[2]).toHaveTextContent('23')
    expect(rows[2]).toHaveTextContent('12.4')
  })

  it('says so when no rain is forecast', () => {
    render(<ForecastView forecast={forecast([day('2026-10-08'), day('2026-10-09')])} />)

    expect(screen.getByText('No rain forecast')).toBeInTheDocument()
  })

  it('shows a dash for a missing value', () => {
    render(
      <ForecastView
        forecast={forecast([day('2026-10-08', { precipitation_mm: null })])}
      />,
    )

    expect(screen.getByTestId('forecast-readout')).toHaveTextContent('– mm')
  })

  it('warns when the forecast is an older one', () => {
    render(
      <ForecastView
        forecast={forecast([day('2026-10-08')], {
          stale: true,
          fetched_at: '2026-10-07T04:30:00Z',
        })}
      />,
    )

    expect(screen.getByRole('status')).toHaveTextContent(
      'The forecast source cannot be reached. This forecast was fetched on',
    )
  })
})
