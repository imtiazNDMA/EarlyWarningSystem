import { useCallback, useMemo, useState } from 'react'

import type { Alert, District } from './api/client'
import { AirQualityLegend } from './features/air-quality/AirQualityLegend'
import { AirQualityView } from './features/air-quality/AirQualityView'
import { useAirQuality } from './features/air-quality/queries'
import { AlertFeed } from './features/alerts/AlertFeed'
import { AlertLegend } from './features/alerts/AlertLegend'
import { AlertList } from './features/alerts/AlertList'
import {
  airQualityAlerts,
  alertsByDistrict,
  highestAlertLevel,
  summariseAlerts,
  weatherAlerts,
} from './features/alerts/alerts'
import { useActiveAlerts, useAlertHistory } from './features/alerts/queries'
import { DistrictMap, type MapFocus } from './features/districts/DistrictMap'
import { DistrictPanel } from './features/districts/DistrictPanel'
import { DistrictPicker } from './features/districts/DistrictPicker'
import { useDistrictBoundaries, useDistricts } from './features/districts/queries'
import { ForecastSection } from './features/forecast/ForecastSection'
import { RunsPanel } from './features/runs/RunsPanel'
import type { Level } from './features/signals/signals'

/** The highest alert level and a tooltip line per map feature, for alerts grouped by district. */
function mapMarks(districts: District[], alerts: Map<string, Alert[]>) {
  const levels = new Map<string, Level>()
  const summaries = new Map<string, string>()
  for (const district of districts) {
    const group = alerts.get(district.id)
    if (!group || district.feature_id === null) continue
    const level = highestAlertLevel(group)
    const summary = summariseAlerts(group)
    if (level) levels.set(district.feature_id, level)
    if (summary) summaries.set(district.feature_id, summary)
  }
  return { levels, summaries }
}

function alertCount(alerts: Map<string, Alert[]>): number {
  let count = 0
  for (const group of alerts.values()) count += group.length
  return count
}

export default function App() {
  const boundaries = useDistrictBoundaries()
  const districts = useDistricts()
  const activeAlerts = useActiveAlerts()
  const alertHistory = useAlertHistory()
  const airQuality = useAirQuality()

  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null)
  const [mapLayer, setMapLayer] = useState<'alerts' | 'pm2_5'>('alerts')
  const [focus, setFocus] = useState<MapFocus | null>(null)
  // The runs panel shares the district panel's place; null follows the newest run
  const [runsOpen, setRunsOpen] = useState(false)
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)

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
  // Each map layer marks its own kind of alert: weather as fill, air quality as outline
  const weather = useMemo(
    () => alertsByDistrict(weatherAlerts(activeAlerts.data ?? [])),
    [activeAlerts.data],
  )
  const air = useMemo(
    () => alertsByDistrict(airQualityAlerts(activeAlerts.data ?? [])),
    [activeAlerts.data],
  )
  const weatherMarks = useMemo(() => mapMarks(districts.data ?? [], weather), [districts.data, weather])
  const airMarks = useMemo(() => mapMarks(districts.data ?? [], air), [districts.data, air])
  const airQualityByDistrict = useMemo(
    () => new Map((airQuality.data ?? []).map((value) => [value.district_id, value])),
    [airQuality.data],
  )
  const pm25ByFeature = useMemo(() => {
    const values = new Map<string, number | null>()
    for (const district of districts.data ?? []) {
      const value = airQualityByDistrict.get(district.id)
      if (value && district.feature_id) values.set(district.feature_id, value.pm2_5_mean_ug_m3)
    }
    return values
  }, [airQualityByDistrict, districts.data])

  const selectFeature = useCallback((featureId: string | null) => {
    setSelectedFeatureId(featureId)
    if (featureId !== null) setRunsOpen(false)
  }, [])
  const selectFromList = useCallback(
    (district: District) => {
      selectFeature(district.feature_id)
      setFocus({ lon: district.lon, lat: district.lat })
    },
    [selectFeature],
  )
  const openRun = useCallback((runId: number) => {
    setSelectedRunId(runId)
    setRunsOpen(true)
  }, [])

  return (
    <main className="relative h-dvh w-full overflow-hidden bg-wash">
      {boundaries.data && (
        <DistrictMap
          boundaries={boundaries.data}
          selectedFeatureId={selectedFeatureId}
          focus={focus}
          onSelect={selectFeature}
          levels={weatherMarks.levels}
          airLevels={airMarks.levels}
          summaries={mapLayer === 'alerts' ? weatherMarks.summaries : airMarks.summaries}
          layer={mapLayer}
          pm25={pm25ByFeature}
        />
      )}

      <header className="plate absolute left-3 top-3 z-10 w-[min(20rem,calc(100%-1.5rem))]">
        <p className="type-label text-signal">Pakistan</p>
        <h1 className="type-display text-xl leading-tight text-ink">Early Warning System</h1>
        <div
          className="mt-3 flex rounded-sm border border-line/40 p-0.5"
          role="group"
          aria-label="Map layer"
        >
          {(['alerts', 'pm2_5'] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={mapLayer === value}
              onClick={() => setMapLayer(value)}
              className={`flex-1 rounded-[2px] px-2 py-1 text-xs font-semibold ${mapLayer === value ? 'bg-ink text-panel' : 'text-ink hover:bg-wash'}`}
            >
              {value === 'alerts' ? 'Weather alerts' : 'Air quality'}
            </button>
          ))}
        </div>
        {districts.data && (
          <DistrictPicker
            districts={districts.data}
            selectedFeatureId={selectedFeatureId}
            onSelect={selectFromList}
          />
        )}
        {mapLayer === 'alerts' && activeAlerts.data && (
          <AlertLegend alertCount={alertCount(weather)} districtCount={weather.size} />
        )}
        {mapLayer === 'pm2_5' && (
          <AirQualityLegend alertCount={alertCount(air)} districtCount={air.size} />
        )}
        {mapLayer === 'pm2_5' && airQuality.isError && (
          <div className="mt-3 border-t border-line/30 pt-3" role="alert">
            <p className="text-sm text-ink/70">Air-quality data could not be loaded.</p>
            <button
              type="button"
              onClick={() => airQuality.refetch()}
              className="mt-2 rounded-sm bg-signal px-3 py-1.5 text-xs font-semibold text-white hover:bg-ink"
            >
              Load air quality again
            </button>
          </div>
        )}
        <button
          type="button"
          aria-pressed={runsOpen}
          onClick={() => setRunsOpen((open) => !open)}
          className="mt-3 w-full rounded-sm border border-line/40 px-2 py-1 text-xs font-semibold text-ink hover:bg-wash"
        >
          Monitoring runs
        </button>
        {districts.isError && (
          <p className="mt-3 text-sm text-ink/70">
            The district list could not be loaded. You can still select districts on
            the map.
          </p>
        )}
      </header>

      {alertHistory.data && districts.data && (
        <div className="absolute bottom-9 left-3 z-10 hidden w-80 md:block">
          <AlertFeed
            title={mapLayer === 'alerts' ? 'Weather alert history' : 'Air-quality alert history'}
            alerts={(mapLayer === 'alerts' ? weatherAlerts : airQualityAlerts)(alertHistory.data)}
            districts={districts.data}
            onSelect={selectFromList}
          />
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

      {runsOpen && (
        <div className="absolute inset-x-3 bottom-9 z-10 md:inset-x-auto md:bottom-auto md:right-3 md:top-3 md:w-80">
          <RunsPanel
            districts={districts.data ?? []}
            selectedRunId={selectedRunId}
            onSelect={setSelectedRunId}
            onClose={() => setRunsOpen(false)}
          />
        </div>
      )}

      {boundaries.data && !runsOpen && (
        <div className="absolute inset-x-3 bottom-9 z-10 md:inset-x-auto md:bottom-auto md:right-3 md:top-3 md:w-80">
          <DistrictPanel
            boundary={selectedBoundary}
            district={selectedDistrict}
            onClose={() => setSelectedFeatureId(null)}
          >
            {selectedDistrict && (
              <>
                <AirQualityView value={airQualityByDistrict.get(selectedDistrict.id)} />
                {activeAlerts.data && (
                  <div className="mb-4 border-b border-line/30 pb-4">
                    <h3 className="type-label mb-3 text-ink/60">Active alerts</h3>
                    <AlertList
                      alerts={byDistrict.get(selectedDistrict.id) ?? []}
                      onOpenRun={openRun}
                    />
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
