import type { BoundaryProperties, District } from '../../api/client'
import { formatDegreesMinutes } from '../../lib/coordinates'

type Props = {
  /** The selected boundary polygon, or null when nothing is selected. */
  boundary: BoundaryProperties | null
  /** The registry entry for the boundary, when it has one. */
  district: District | undefined
  onClose: () => void
}

export function DistrictPanel({ boundary, district, onClose }: Props) {
  if (boundary === null) {
    return (
      <aside className="plate hidden md:block" aria-label="Selected district">
        <p className="text-sm text-ink/70">
          Select a district on the map or from the list.
        </p>
      </aside>
    )
  }

  return (
    <aside className="plate" aria-label="Selected district">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="type-label text-signal">{boundary.province}</p>
          <h2 className="type-display mt-1 text-2xl leading-tight text-ink">
            {boundary.name_en}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Clear selection"
          className="-mr-1 -mt-1 grid size-8 shrink-0 place-items-center rounded-sm text-ink/60 hover:bg-wash hover:text-ink"
        >
          <svg viewBox="0 0 16 16" className="size-3.5" aria-hidden="true">
            <path
              d="M2 2l12 12M14 2L2 14"
              stroke="currentColor"
              strokeWidth="1.75"
              fill="none"
            />
          </svg>
        </button>
      </div>

      {district ? (
        <dl className="mt-4 border-t border-line/30 pt-3">
          <dt className="type-label text-ink/60">Forecast point</dt>
          <dd className="mt-0.5 font-mono text-sm text-ink">
            {formatDegreesMinutes(district.lat, district.lon)}
          </dd>
        </dl>
      ) : (
        <p className="mt-4 border-t border-line/30 pt-3 text-sm text-ink/70">
          No forecasts or alerts are produced for this area.
        </p>
      )}
    </aside>
  )
}
