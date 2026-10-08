import type { AirQuality } from '../../api/client'

export function AirQualityView({ value }: { value: AirQuality | undefined }) {
  return (
    <section className="mb-4 border-b border-line/30 pb-4">
      <h3 className="type-label text-ink/60">Air quality</h3>
      {value ? (
        <div className="mt-2 flex items-end justify-between gap-4">
          <div>
            <p className="font-mono text-3xl font-semibold text-ink">
              {value.pm2_5_mean_ug_m3 === null ? '—' : value.pm2_5_mean_ug_m3.toFixed(1)}
            </p>
            <p className="text-xs text-ink/60">µg/m³ daily mean PM2.5</p>
          </div>
          <p className="text-right font-mono text-xs text-ink/55">Forecast for {value.date}</p>
        </div>
      ) : (
        <p className="mt-2 text-sm text-ink/70">No air-quality forecast available.</p>
      )}
    </section>
  )
}
