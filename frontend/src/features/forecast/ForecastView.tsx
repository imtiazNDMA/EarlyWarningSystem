import { useState } from 'react'

import type { DailyForecast, Forecast } from '../../api/client'

// Chart colours: one per chart, both clear of the hues reserved for alert severity
const TEMPERATURE = '#3F5B6B'
const RAIN = '#2F6DA8'

// Shared geometry so the two charts line up day for day
const WIDTH = 288
const GUTTER = 28
const PLOT_WIDTH = WIDTH - GUTTER
const TEMPERATURE_HEIGHT = 92
const RAIN_HEIGHT = 56
const BAR_WIDTH = 10
// Keeps a dry week from stretching 0.3 mm to the top of the chart
const MIN_RAIN_SCALE_MM = 10

const WEEKDAY = new Intl.DateTimeFormat('en-GB', { weekday: 'short' })
const DAY_MONTH = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' })
const FETCHED = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

/** Parse a YYYY-MM-DD date as a local calendar day, not a UTC instant. */
function calendarDay(isoDate: string): Date {
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function dayLabel(isoDate: string): string {
  const date = calendarDay(isoDate)
  return `${WEEKDAY.format(date)} ${DAY_MONTH.format(date)}`
}

function degrees(value: number | null): string {
  return value === null ? '–' : `${Math.round(value)}°`
}

function millimetres(value: number | null): string {
  return value === null ? '–' : value.toFixed(1)
}

function columnCentre(index: number, count: number): number {
  return GUTTER + (PLOT_WIDTH / count) * (index + 0.5)
}

type HoverProps = {
  count: number
  height: number
  active: number
  onActivate: (index: number) => void
  testIds?: boolean
}

/** Full-height columns: the active one is tinted, and each is a wide hover target. */
function DayColumns({ count, height, active, onActivate, testIds }: HoverProps) {
  const step = PLOT_WIDTH / count
  return (
    <>
      {Array.from({ length: count }, (_, index) => (
        <rect
          key={index}
          data-testid={testIds ? `forecast-day-${index}` : undefined}
          x={GUTTER + step * index}
          y={0}
          width={step}
          height={height}
          fill={index === active ? 'var(--color-wash)' : 'transparent'}
          onPointerEnter={() => onActivate(index)}
          onPointerDown={() => onActivate(index)}
        />
      ))}
    </>
  )
}

function GridLine({ y, label }: { y: number; label: string }) {
  return (
    <g>
      <line
        x1={GUTTER}
        x2={WIDTH}
        y1={y}
        y2={y}
        stroke="var(--color-line)"
        strokeOpacity={0.25}
      />
      <text x={GUTTER - 5} y={y + 3} textAnchor="end" className="fill-ink/60 text-[9px]">
        {label}
      </text>
    </g>
  )
}

function TemperatureChart({ days, active, onActivate }: ChartProps) {
  const highs = days.flatMap((d) => (d.temperature_max_c === null ? [] : [d.temperature_max_c]))
  const lows = days.flatMap((d) => (d.temperature_min_c === null ? [] : [d.temperature_min_c]))
  if (highs.length === 0 || lows.length === 0) {
    return <p className="text-sm text-ink/70">No temperature forecast.</p>
  }

  // Round outwards to 5° so the grid lines land on round numbers
  const top = Math.ceil((Math.max(...highs) + 1) / 5) * 5
  const bottom = Math.floor((Math.min(...lows) - 1) / 5) * 5
  const padding = 12
  const y = (value: number) =>
    padding + ((top - value) / (top - bottom)) * (TEMPERATURE_HEIGHT - padding * 2)

  const hottest = highs.indexOf(Math.max(...highs))
  const coldest = lows.indexOf(Math.min(...lows))

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${TEMPERATURE_HEIGHT}`}
      className="block w-full"
      role="img"
      aria-label="Daily temperature range in degrees Celsius"
    >
      <DayColumns
        count={days.length}
        height={TEMPERATURE_HEIGHT}
        active={active}
        onActivate={onActivate}
        testIds
      />
      <GridLine y={y(top)} label={`${top}°`} />
      <GridLine y={y(bottom)} label={`${bottom}°`} />
      {days.map((day, index) => {
        if (day.temperature_max_c === null || day.temperature_min_c === null) return null
        const x = columnCentre(index, days.length)
        const yHigh = y(day.temperature_max_c)
        const yLow = y(day.temperature_min_c)
        return (
          <g key={day.date} pointerEvents="none">
            <rect
              x={x - BAR_WIDTH / 2}
              y={yHigh}
              width={BAR_WIDTH}
              height={Math.max(yLow - yHigh, BAR_WIDTH)}
              rx={4}
              fill={TEMPERATURE}
            />
            {/* Label only the extremes; the readout carries every other value */}
            {index === hottest && (
              <text x={x} y={yHigh - 4} textAnchor="middle" className="fill-ink text-[9px] font-semibold">
                {degrees(day.temperature_max_c)}
              </text>
            )}
            {index === coldest && (
              <text x={x} y={yLow + 11} textAnchor="middle" className="fill-ink text-[9px] font-semibold">
                {degrees(day.temperature_min_c)}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}

function RainChart({ days, active, onActivate }: ChartProps) {
  const amounts = days.map((d) => d.precipitation_mm ?? 0)
  const wettest = Math.max(...amounts)
  const top = Math.max(Math.ceil(wettest / 10) * 10, MIN_RAIN_SCALE_MM)
  const baseline = RAIN_HEIGHT - 16
  const plotTop = 12
  const y = (value: number) => baseline - (value / top) * (baseline - plotTop)
  const wettestIndex = amounts.indexOf(wettest)

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${RAIN_HEIGHT}`}
      className="block w-full"
      role="img"
      aria-label="Daily rainfall in millimetres"
    >
      <DayColumns
        count={days.length}
        height={RAIN_HEIGHT}
        active={active}
        onActivate={onActivate}
      />
      <GridLine y={y(top)} label={`${top}`} />
      <GridLine y={baseline} label="0" />
      {days.map((day, index) => {
        const x = columnCentre(index, days.length)
        const amount = amounts[index]
        const barTop = y(amount)
        return (
          <g key={day.date} pointerEvents="none">
            {amount > 0 && (
              // Rounded at the top only: the bar stands on the baseline
              <path
                d={roundedTopBar(x - BAR_WIDTH / 2, barTop, BAR_WIDTH, baseline - barTop)}
                fill={RAIN}
              />
            )}
            {wettest > 0 && index === wettestIndex && (
              <text x={x} y={barTop - 4} textAnchor="middle" className="fill-ink text-[9px] font-semibold">
                {millimetres(amount)}
              </text>
            )}
            <text
              x={x}
              y={RAIN_HEIGHT - 3}
              textAnchor="middle"
              className={`text-[9px] ${index === active ? 'fill-ink font-semibold' : 'fill-ink/60'}`}
            >
              {WEEKDAY.format(calendarDay(day.date))}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function roundedTopBar(x: number, y: number, width: number, height: number): string {
  const radius = Math.min(4, width / 2, height)
  return [
    `M${x},${y + height}`,
    `V${y + radius}`,
    `Q${x},${y} ${x + radius},${y}`,
    `H${x + width - radius}`,
    `Q${x + width},${y} ${x + width},${y + radius}`,
    `V${y + height}`,
    'Z',
  ].join(' ')
}

type ChartProps = {
  days: DailyForecast[]
  active: number
  onActivate: (index: number) => void
}

export function ForecastView({ forecast }: { forecast: Forecast }) {
  const { days } = forecast
  const [active, setActive] = useState(0)
  // A refreshed forecast can be shorter than the one it replaces
  const day = days[Math.min(active, days.length - 1)]

  if (!day) {
    return <p className="text-sm text-ink/70">The forecast source returned no days.</p>
  }

  const chance = day.precipitation_probability_pct
  const dry = days.every((d) => !d.precipitation_mm)
  const fetched = FETCHED.format(new Date(forecast.fetched_at))

  return (
    <div>
      {forecast.stale && (
        <p role="status" className="mb-3 border-l-2 border-ink pl-2 text-sm text-ink">
          The forecast source cannot be reached. This forecast was fetched on {fetched}.
        </p>
      )}

      <p data-testid="forecast-readout" className="flex flex-wrap items-baseline gap-x-3 text-sm text-ink">
        <span className="font-semibold">{dayLabel(day.date)}</span>
        <span className="font-mono">
          {degrees(day.temperature_max_c)} / {degrees(day.temperature_min_c)}
        </span>
        <span className="font-mono">
          {millimetres(day.precipitation_mm)} mm
          {chance !== null && <span className="text-ink/60"> · {Math.round(chance)}% chance</span>}
        </span>
      </p>

      <div onPointerLeave={() => setActive(0)}>
        <h3 className="type-label mt-3 text-ink/60">Temperature, °C</h3>
        <TemperatureChart days={days} active={active} onActivate={setActive} />

        <h3 className="type-label mt-2 text-ink/60">Rainfall, mm</h3>
        <RainChart days={days} active={active} onActivate={setActive} />
        {dry && <p className="-mt-9 mb-5 text-center text-xs text-ink/60">No rain forecast</p>}
      </div>

      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-ink/70 hover:text-ink">Show as a table</summary>
        <table className="mt-2 w-full text-left font-mono text-xs">
          <thead>
            <tr className="text-ink/60">
              <th className="py-1 font-sans font-semibold">Day</th>
              <th className="py-1 text-right font-sans font-semibold">High °C</th>
              <th className="py-1 text-right font-sans font-semibold">Low °C</th>
              <th className="py-1 text-right font-sans font-semibold">Rain mm</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d.date} className="border-t border-line/20">
                <td className="py-1 font-sans">{dayLabel(d.date)}</td>
                <td className="py-1 text-right">{d.temperature_max_c ?? '–'}</td>
                <td className="py-1 text-right">{d.temperature_min_c ?? '–'}</td>
                <td className="py-1 text-right">{millimetres(d.precipitation_mm)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>

      {!forecast.stale && (
        <p className="mt-2 text-xs text-ink/50">Open-Meteo forecast, fetched {fetched}</p>
      )}
    </div>
  )
}
