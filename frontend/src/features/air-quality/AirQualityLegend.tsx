const STOPS = [
  ['< 55', '#CDE5DF'],
  ['55–149', '#79B9AD'],
  ['150–249', '#327F83'],
  ['250+', '#14303F'],
] as const

export function AirQualityLegend() {
  return (
    <div className="mt-3 border-t border-line/30 pt-3">
      <p className="type-label text-ink/60">Daily mean PM2.5 · µg/m³</p>
      <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink">
        {STOPS.map(([label, colour]) => (
          <li key={label} className="flex items-center gap-1.5">
            <span className="size-3 rounded-[2px] border border-ink/20" style={{ background: colour }} />
            {label}
          </li>
        ))}
      </ul>
    </div>
  )
}
