import type { Alert, District } from '../../api/client'
import { AlertCard } from './AlertList'

type Props = {
  alerts: Alert[]
  districts: District[]
  onSelect: (district: District) => void
  /** Names the kind of alert listed, when the feed is narrowed to one. */
  title?: string
}

/** Chronological nationwide lifecycle feed; selecting one opens its district. */
export function AlertFeed({ alerts, districts, onSelect, title = 'Alert history' }: Props) {
  const districtById = new Map(districts.map((district) => [district.id, district]))

  return (
    <section className="plate mt-2 max-h-[min(19rem,40dvh)] overflow-y-auto" aria-label={title}>
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="type-label text-ink/60">{title}</h2>
        <span className="font-mono text-xs text-ink/55">{alerts.length}</span>
      </div>
      {alerts.length === 0 ? (
        <p className="mt-2 text-sm text-ink/70">No alerts have been issued.</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {alerts.map((alert) => {
            const district = districtById.get(alert.district_id)
            return (
              <li key={alert.id}>
                <button
                  type="button"
                  disabled={!district}
                  onClick={() => district && onSelect(district)}
                  className="w-full rounded-sm py-1 text-left hover:bg-wash/70 disabled:cursor-default"
                >
                  <AlertCard alert={alert} compact />
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
