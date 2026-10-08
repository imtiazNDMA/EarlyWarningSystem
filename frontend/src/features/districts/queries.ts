import { useQuery } from '@tanstack/react-query'
import type { FeatureCollection, MultiPolygon } from 'geojson'

import { api, type BoundaryProperties, type District } from '../../api/client'

export type DistrictBoundaries = FeatureCollection<MultiPolygon, BoundaryProperties>

// The registry and boundaries only change when the backend is redeployed
const STATIC_DATA = { staleTime: Infinity, retry: 1 }

export function useDistricts() {
  return useQuery({
    queryKey: ['districts'],
    queryFn: async (): Promise<District[]> => {
      const { data, error } = await api.GET('/api/districts')
      if (error) throw new Error('The district list could not be loaded.')
      return data
    },
    ...STATIC_DATA,
  })
}

export function useDistrictBoundaries() {
  return useQuery({
    queryKey: ['districts', 'geojson'],
    queryFn: async (): Promise<DistrictBoundaries> => {
      const { data, error } = await api.GET('/api/districts/geojson')
      if (error) throw new Error('District boundaries could not be loaded.')
      // The schema types geometry loosely; the backend always sends MultiPolygons
      return data as unknown as DistrictBoundaries
    },
    ...STATIC_DATA,
  })
}
