import { useCallback, useMemo, useState } from 'react'

import type { District } from './api/client'
import { AlertFeed } from './features/alerts/AlertFeed'
import { AlertLegend } from './features/alerts/AlertLegend'
import { AlertList } from './features/alerts/AlertList'
import { alertsByDistrict, highestAlertLevel, summariseAlerts } from './features/alerts/alerts'
import { useActiveAlerts, useAlertHistory } from './features/alerts/queries'
import { DistrictMap, type MapFocus } from './features/districts/DistrictMap'
import { DistrictPanel } from './features/districts/DistrictPanel'
import { DistrictPicker } from './features/districts/DistrictPicker'
import { useDistrictBoundaries, useDistricts } from './features/districts/queries'
import { ForecastSection } from './features/forecast/ForecastSection'
import type { Level } from './features/signals/signals'

export default function App() {
  const boundaries = useDistrictBoundaries()
  const districts = useDistricts()
  const activeAlerts = useActiveAlerts()
  const alertHistory = useAlertHistory()

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

  const byDistrict = useMemo(
    () => alertsByDistrict(activeAlerts.data ?? []),
    [activeAlerts.data],
  )
  const { levels, summaries } = useMemo(() => {
    const levels = new Map<string, Level>()
    const summaries = new Map<string, string>()
    for (const district of districts.data ?? []) {
      const alerts = byDistrict.get(district.id)
      if (!alerts || district.feature_id === null) continue
      const level = highestAlertLevel(alerts)
      const summary = summariseAlerts(alerts)
      if (level) levels.set(district.feature_id, level)
      if (summary) summaries.set(district.feature_id, summary)
    }
    return { levels, summaries }
  }, [byDistrict, districts.data])

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
          levels={levels}
          summaries={summaries}
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
        {activeAlerts.data && (
          <AlertLegend alertCount={activeAlerts.data.length} districtCount={byDistrict.size} />
        )}
        {districts.isError && (
          <p className="mt-3 text-sm text-ink/70">
            The district list could not be loaded. You can still select districts on
            the map.
          </p>
        )}
      </header>

      {alertHistory.data && districts.data && (
        <div className="absolute bottom-9 left-3 z-10 hidden w-80 md:block">
          <AlertFeed alerts={alertHistory.data} districts={districts.data} onSelect={selectFromList} />
        </div>
      )}

      {(activeAlerts.isError || alertHistory.isError) && (
        <div className="plate absolute bottom-9 left-3 z-10 w-[min(20rem,calc(100%-1.5rem))]" role="alert">
          <p className="text-sm text-ink">Alert information could not be loaded.</p>
          <button
            type="button"
            onClick={() => {
              activeAlerts.refetch()
              alertHistory.refetch()
            }}
            className="mt-2 rounded-sm bg-signal px-3 py-1.5 text-sm font-semibold text-white hover:bg-ink"
          >
            Load alerts again
          </button>
        </div>
      )}

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
              <>
                {activeAlerts.data && (
                  <div className="mb-4 border-b border-line/30 pb-4">
                    <h3 className="type-label mb-3 text-ink/60">Active alerts</h3>
                    <AlertList alerts={byDistrict.get(selectedDistrict.id) ?? []} />
                  </div>
                )}
                {/* Keyed so the hovered day resets when another district is chosen */}
                <ForecastSection key={selectedDistrict.id} districtId={selectedDistrict.id} />
              </>
            )}
          </DistrictPanel>
        </div>
      )}
    </main>
  )
}
