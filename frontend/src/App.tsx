import { useCallback, useMemo, useState } from 'react'

import type { District } from './api/client'
import { DistrictMap, type MapFocus } from './features/districts/DistrictMap'
import { DistrictPanel } from './features/districts/DistrictPanel'
import { DistrictPicker } from './features/districts/DistrictPicker'
import { useDistrictBoundaries, useDistricts } from './features/districts/queries'
import { ForecastSection } from './features/forecast/ForecastSection'

export default function App() {
  const boundaries = useDistrictBoundaries()
  const districts = useDistricts()

  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null)
  const [focus, setFocus] = useState<MapFocus | null>(null)

  const selectedBoundary = useMemo(
    () =>
      boundaries.data?.features.find(
        (feature) => feature.properties.feature_id === selectedFeatureId,
      )?.properties ?? null,
    [boundaries.data, selectedFeatureId],
  )
  const selectedDistrict = districts.data?.find(
    (district) => district.feature_id === selectedFeatureId,
  )

  const selectFromList = useCallback((district: District) => {
    setSelectedFeatureId(district.feature_id)
    setFocus({ lon: district.lon, lat: district.lat })
  }, [])

  return (
    <main className="relative h-dvh w-full overflow-hidden bg-wash">
      {boundaries.data && (
        <DistrictMap
          boundaries={boundaries.data}
          selectedFeatureId={selectedFeatureId}
          focus={focus}
          onSelect={setSelectedFeatureId}
        />
      )}

      <header className="plate absolute left-3 top-3 z-10 w-[min(20rem,calc(100%-1.5rem))]">
        <p className="type-label text-signal">Pakistan</p>
        <h1 className="type-display text-xl leading-tight text-ink">Early Warning System</h1>
        {districts.data && (
          <DistrictPicker
            districts={districts.data}
            selectedFeatureId={selectedFeatureId}
            onSelect={selectFromList}
          />
        )}
        {districts.isError && (
          <p className="mt-3 text-sm text-ink/70">
            The district list could not be loaded. You can still select districts on
            the map.
          </p>
        )}
      </header>

      {boundaries.isPending && (
        <p className="absolute inset-0 grid place-items-center text-sm text-ink/70" role="status">
          Loading district boundaries…
        </p>
      )}

      {boundaries.isError && (
        <div className="absolute inset-0 grid place-items-center p-6" role="alert">
          <div className="plate max-w-sm">
            <h2 className="type-display text-lg text-ink">District boundaries could not be loaded</h2>
            <p className="mt-2 text-sm text-ink/70">
              Check that the API is running, then load them again.
            </p>
            <button
              type="button"
              onClick={() => boundaries.refetch()}
              className="mt-4 rounded-sm bg-signal px-3 py-1.5 text-sm font-semibold text-white hover:bg-ink"
            >
              Load boundaries again
            </button>
          </div>
        </div>
      )}

      {boundaries.data && (
        <div className="absolute inset-x-3 bottom-9 z-10 md:inset-x-auto md:bottom-auto md:right-3 md:top-3 md:w-80">
          <DistrictPanel
            boundary={selectedBoundary}
            district={selectedDistrict}
            onClose={() => setSelectedFeatureId(null)}
          >
            {selectedDistrict && (
              // Keyed so the hovered day resets when another district is chosen
              <ForecastSection key={selectedDistrict.id} districtId={selectedDistrict.id} />
            )}
          </DistrictPanel>
        </div>
      )}
    </main>
  )
}
