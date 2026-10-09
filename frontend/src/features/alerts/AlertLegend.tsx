import { LEVEL_COLOURS, LEVEL_LABELS, LEVELS } from '../signals/signals'

export function AlertLegend({ alertCount, districtCount }: { alertCount: number; districtCount: number }) {
  return (
    <div className="mt-3 border-t border-line/30 pt-3">
      <p className="type-label text-ink/60">Highest active weather alert</p>
      <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink">
        {LEVELS.map((level) => (
          <li key={level} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="size-3 rounded-[2px] border border-ink/25"
              style={{ background: LEVEL_COLOURS[level] }}
            />
            {LEVEL_LABELS[level]}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-xs text-ink/60">
        {alertCount === 0
          ? 'No active weather alerts.'
          : `${alertCount} active weather ${alertCount === 1 ? 'alert' : 'alerts'} across ${districtCount} ${districtCount === 1 ? 'district' : 'districts'}.`}
      </p>
    </div>
  )
}
