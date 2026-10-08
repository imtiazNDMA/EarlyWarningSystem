import { useQuery } from '@tanstack/react-query'

import { api, type CurrentSignals } from '../../api/client'

/** Signals from the latest successful monitoring cycle. */
export function useCurrentSignals() {
  return useQuery({
    queryKey: ['signals'],
    queryFn: async (): Promise<CurrentSignals> => {
      const { data, error } = await api.GET('/api/signals')
      if (error) throw new Error('Hazard signals could not be loaded.')
      return data
    },
    // Pick up a new cycle without a page reload
    refetchInterval: 60 * 1000,
    staleTime: 30 * 1000,
  })
}
