import { LEVEL_COLOURS, LEVEL_LABELS, LEVELS } from '../signals/signals'
import { AirQualityAttribution } from './AirQualityAttribution'

const STOPS = [
  ['< 55', '#CDE5DF'],
  ['55–149', '#79B9AD'],
  ['150–249', '#327F83'],
  ['250+', '#14303F'],
] as const

export function AirQualityLegend({ alertCount, districtCount }: { alertCount: number; districtCount: number }) {
  return (
    <div className="mt-3 border-t border-line/30 pt-3">
      <p className="type-label text-ink/60">
        {/* Capitals would turn the micro sign into an M */}
        Daily mean PM2.5 · <span className="normal-case">μg/m³</span>
      </p>
      <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink">
        {STOPS.map(([label, colour]) => (
          <li key={label} className="flex items-center gap-1.5">
            <span className="size-3 rounded-[2px] border border-ink/20" style={{ background: colour }} />
            {label}
          </li>
        ))}
      </ul>
      <p className="type-label mt-3 text-ink/60">Outline: active air-quality alert</p>
      <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink">
        {LEVELS.map((level) => (
          <li key={level} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-3 rounded-[2px] border-2"
              style={{ borderColor: LEVEL_COLOURS[level] }}
            />
            {LEVEL_LABELS[level]}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-ink/60">
        {alertCount === 0
          ? 'No active air-quality alerts.'
          : `${alertCount} active air-quality ${alertCount === 1 ? 'alert' : 'alerts'} across ${districtCount} ${districtCount === 1 ? 'district' : 'districts'}.`}
      </p>
      <AirQualityAttribution />
    </div>
  )
}
