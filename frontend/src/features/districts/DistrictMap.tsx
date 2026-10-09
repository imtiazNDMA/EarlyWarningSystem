import '../../lib/maplibreWorker'

import { Map as MapLibreMap, NavigationControl } from 'maplibre-gl'
import { useEffect, useRef, useState } from 'react'

import type { BoundaryProperties } from '../../api/client'
import { LEVEL_COLOURS, type Level } from '../signals/signals'
import type { DistrictBoundaries } from './queries'

// Free, key-less vector base map
const BASEMAP_STYLE = 'https://tiles.openfreemap.org/styles/positron'
const PAKISTAN_BOUNDS: [number, number, number, number] = [60.8, 23.5, 77.9, 37.2]

const SOURCE = 'districts'
const FILL_LAYER = 'districts-fill'

const INK = '#14303F'
const SIGNAL = '#0E6F77'
const DISTRICT_TINT = '#8DBAB5'
const UNREGISTERED_TINT = '#A9B4B8'

export type MapFocus = { lon: number; lat: number }

type Hover = { x: number; y: number; properties: BoundaryProperties }

type Props = {
  boundaries: DistrictBoundaries
  selectedFeatureId: string | null
  /** Position to move to; change the object to move again. */
  focus: MapFocus | null
  onSelect: (featureId: string | null) => void
  /** Highest active weather alert level per feature_id; features without one are absent. */
  levels: Map<string, Level>
  /** Highest active air-quality alert level per feature_id, outlined on the PM2.5 layer. */
  airLevels: Map<string, Level>
  /** One-line summary per feature_id of the alerts the layer shows, for the hover tooltip. */
  summaries: Map<string, string>
  layer: 'alerts' | 'pm2_5'
  pm25: Map<string, number | null>
}

export function DistrictMap({
  boundaries,
  selectedFeatureId,
  focus,
  onSelect,
  levels,
  airLevels,
  summaries,
  layer,
  pm25,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const [ready, setReady] = useState(false)
  const [hover, setHover] = useState<Hover | null>(null)

  // Keep the latest callback without re-creating the map
  const onSelectRef = useRef(onSelect)
  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  useEffect(() => {
    if (!containerRef.current) return

    const map = new MapLibreMap({
      container: containerRef.current,
      style: BASEMAP_STYLE,
      bounds: PAKISTAN_BOUNDS,
      fitBoundsOptions: { padding: 32 },
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right')

    let hoveredId: string | null = null
    const setHovered = (id: string | null) => {
      if (hoveredId === id) return
      if (hoveredId !== null) {
        map.setFeatureState({ source: SOURCE, id: hoveredId }, { hover: false })
      }
      if (id !== null) {
        map.setFeatureState({ source: SOURCE, id }, { hover: true })
      }
      hoveredId = id
    }

    // 'style.load' fires before the base map's tiles arrive, so the districts
    // appear without waiting for them
    map.once('style.load', () => {
      // Draw districts under the base map's labels so place names stay readable
      const firstLabel = map.getStyle().layers.find((layer) => layer.type === 'symbol')?.id

      map.addSource(SOURCE, {
        type: 'geojson',
        data: boundaries,
        promoteId: 'feature_id',
      })
      map.addLayer(
        {
          id: FILL_LAYER,
          type: 'fill',
          source: SOURCE,
          paint: {
            // An active alert level always wins; selection shows as an outline
            'fill-color': [
              'case',
              ['==', ['feature-state', 'view'], 'pm2_5'],
              [
                'step', ['coalesce', ['feature-state', 'pm2_5'], -1],
                UNREGISTERED_TINT, 0, '#CDE5DF', 55, '#79B9AD',
                150, '#327F83', 250, '#14303F',
              ],
              ['match',
              ['coalesce', ['feature-state', 'level'], 'none'],
              'moderate',
              LEVEL_COLOURS.moderate,
              'severe',
              LEVEL_COLOURS.severe,
              'extreme',
              LEVEL_COLOURS.extreme,
              [
                'case',
                ['boolean', ['feature-state', 'selected'], false],
                SIGNAL,
                ['==', ['get', 'district_id'], null],
                UNREGISTERED_TINT,
                DISTRICT_TINT,
              ]],
            ],
            'fill-opacity': [
              'case',
              ['==', ['feature-state', 'view'], 'pm2_5'],
              ['case', ['boolean', ['feature-state', 'hover'], false], 0.85, 0.68],
              ['!=', ['coalesce', ['feature-state', 'level'], 'none'], 'none'],
              ['case', ['boolean', ['feature-state', 'hover'], false], 0.85, 0.7],
              ['boolean', ['feature-state', 'selected'], false],
              0.5,
              ['boolean', ['feature-state', 'hover'], false],
              0.6,
              0.3,
            ],
          },
        },
        firstLabel,
      )
      map.addLayer(
        {
          id: 'districts-line',
          type: 'line',
          source: SOURCE,
          paint: {
            'line-color': INK,
            'line-opacity': 0.55,
            'line-width': ['interpolate', ['linear'], ['zoom'], 4, 0.4, 8, 1.2],
          },
        },
        firstLabel,
      )
      // On the PM2.5 layer the fill is the reading, so an alert is an outline
      map.addLayer(
        {
          id: 'districts-air-alert-line',
          type: 'line',
          source: SOURCE,
          paint: {
            'line-color': [
              'match',
              ['coalesce', ['feature-state', 'air_level'], 'none'],
              'moderate',
              LEVEL_COLOURS.moderate,
              'severe',
              LEVEL_COLOURS.severe,
              'extreme',
              LEVEL_COLOURS.extreme,
              INK,
            ],
            'line-width': ['interpolate', ['linear'], ['zoom'], 4, 2, 8, 4],
            'line-opacity': [
              'case',
              [
                'all',
                ['==', ['feature-state', 'view'], 'pm2_5'],
                ['!=', ['coalesce', ['feature-state', 'air_level'], 'none'], 'none'],
              ],
              1,
              0,
            ],
          },
        },
        firstLabel,
      )
      map.addLayer(
        {
          id: 'districts-selected-line',
          type: 'line',
          source: SOURCE,
          paint: {
            'line-color': INK,
            'line-width': 2.5,
            'line-opacity': [
              'case',
              ['boolean', ['feature-state', 'selected'], false],
              1,
              0,
            ],
          },
        },
        firstLabel,
      )

      map.on('mousemove', FILL_LAYER, (event) => {
        const feature = event.features?.[0]
        if (!feature) return
        map.getCanvas().style.cursor = 'pointer'
        setHovered(String(feature.id))
        setHover({
          x: event.point.x,
          y: event.point.y,
          properties: feature.properties as BoundaryProperties,
        })
      })
      map.on('mouseleave', FILL_LAYER, () => {
        map.getCanvas().style.cursor = ''
        setHovered(null)
        setHover(null)
      })
      map.on('click', (event) => {
        const [feature] = map.queryRenderedFeatures(event.point, { layers: [FILL_LAYER] })
        onSelectRef.current(feature ? String(feature.id) : null)
      })

      setReady(true)
    })

    return () => {
      mapRef.current = null
      map.remove()
    }
  }, [boundaries])

  // Mirror the selection into feature state
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || selectedFeatureId === null) return
    map.setFeatureState({ source: SOURCE, id: selectedFeatureId }, { selected: true })
    return () => {
      // The map may already be removed when this runs during unmount
      if (mapRef.current === map) {
        map.setFeatureState({ source: SOURCE, id: selectedFeatureId }, { selected: false })
      }
    }
  }, [selectedFeatureId, ready])

  // Mirror active alert levels into feature state
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    for (const feature of boundaries.features) {
      const id = feature.properties.feature_id
      map.setFeatureState(
        { source: SOURCE, id },
        { level: levels.get(id) ?? null, air_level: airLevels.get(id) ?? null },
      )
    }
  }, [levels, airLevels, boundaries, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    for (const feature of boundaries.features) {
      const id = feature.properties.feature_id
      map.setFeatureState(
        { source: SOURCE, id },
        { pm2_5: pm25.get(id) ?? null, view: layer },
      )
    }
  }, [pm25, layer, boundaries, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || focus === null) return
    // Not marked essential, so it jumps instead of animating under reduced motion
    map.flyTo({ center: [focus.lon, focus.lat], zoom: Math.max(map.getZoom(), 6.5) })
  }, [focus, ready])

  return (
    <div className="absolute inset-0">
      <div
        ref={containerRef}
        className="size-full"
        role="application"
        aria-label="Map of Pakistan's districts. Use the district list to select by keyboard."
      />
      {hover && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-sm bg-ink px-2.5 py-1.5 text-panel shadow-md"
          style={{ left: hover.x, top: hover.y - 12 }}
        >
          <p className="text-sm font-semibold leading-tight">{hover.properties.name_en}</p>
          <p className="type-label text-panel/70">{hover.properties.province}</p>
          {layer === 'pm2_5' && (
            <p className="mt-1 text-xs">
              PM2.5: {pm25.get(hover.properties.feature_id)?.toFixed(1) ?? 'No data'}{' '}
              {pm25.get(hover.properties.feature_id) !== null &&
                pm25.get(hover.properties.feature_id) !== undefined &&
                'μg/m³'}
            </p>
          )}
          {summaries.has(hover.properties.feature_id) && (
            <p className="mt-1 text-xs">{summaries.get(hover.properties.feature_id)}</p>
          )}
        </div>
      )}
    </div>
  )
}
