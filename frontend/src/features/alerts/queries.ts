import { useQuery } from '@tanstack/react-query'

import { api, type Alert } from '../../api/client'

/** Alerts that currently govern the public map and district panels. */
export function useActiveAlerts() {
  return useQuery({
    queryKey: ['alerts', 'active'],
    queryFn: async (): Promise<Alert[]> => {
      const { data, error } = await api.GET('/api/alerts', {
        params: { query: { status: 'active', limit: 500 } },
      })
      if (error) throw new Error('Active alerts could not be loaded.')
      return data
    },
    refetchInterval: 60 * 1000,
    staleTime: 30 * 1000,
  })
}

/** Full alert history for the chronological lifecycle feed. */
export function useAlertHistory() {
  return useQuery({
    queryKey: ['alerts', 'history'],
    queryFn: async (): Promise<Alert[]> => {
      const { data, error } = await api.GET('/api/alerts', {
        params: { query: { limit: 500 } },
      })
      if (error) throw new Error('Alert history could not be loaded.')
      return data
    },
    refetchInterval: 60 * 1000,
    staleTime: 30 * 1000,
  })
}
