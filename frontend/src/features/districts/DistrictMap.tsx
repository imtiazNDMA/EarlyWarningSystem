import '../../lib/maplibreWorker'

import { Map as MapLibreMap, NavigationControl } from 'maplibre-gl'
import { useEffect, useRef, useState } from 'react'

import type { BoundaryProperties } from '../../api/client'
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
}

export function DistrictMap({ boundaries, selectedFeatureId, focus, onSelect }: Props) {
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

    map.on('load', () => {
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
            'fill-color': [
              'case',
              ['boolean', ['feature-state', 'selected'], false],
              SIGNAL,
              ['==', ['get', 'district_id'], null],
              UNREGISTERED_TINT,
              DISTRICT_TINT,
            ],
            'fill-opacity': [
              'case',
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
        </div>
      )}
    </div>
  )
}
