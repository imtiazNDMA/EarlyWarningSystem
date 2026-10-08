import { useQuery } from '@tanstack/react-query'

import { api, type AirQuality } from '../../api/client'

export function useAirQuality() {
  return useQuery({
    queryKey: ['air-quality'],
    queryFn: async (): Promise<AirQuality[]> => {
      const { data, error } = await api.GET('/api/air-quality')
      if (error) throw new Error('Air-quality data could not be loaded.')
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}
