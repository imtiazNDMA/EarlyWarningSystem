import { useQuery } from '@tanstack/react-query'

import { api, type Forecast } from '../../api/client'
import { ForecastView } from './ForecastView'

function useForecast(districtId: string) {
  return useQuery({
    queryKey: ['districts', districtId, 'forecast'],
    queryFn: async (): Promise<Forecast> => {
      const { data, error } = await api.GET('/api/districts/{district_id}/forecast', {
        params: { path: { district_id: districtId } },
      })
      if (error) throw new Error('The forecast could not be loaded.')
      return data
    },
    // The backend refreshes its own copy; no need to ask again for a while
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}

/** Loads and shows the forecast for one district. */
export function ForecastSection({ districtId }: { districtId: string }) {
  const forecast = useForecast(districtId)

  if (forecast.isPending) {
    return (
      <p role="status" className="text-sm text-ink/70">
        Loading forecast…
      </p>
    )
  }

  if (forecast.isError) {
    return (
      <div role="alert">
        <p className="text-sm text-ink">
          The forecast could not be loaded. The forecast source may be unavailable.
        </p>
        <button
          type="button"
          onClick={() => forecast.refetch()}
          className="mt-2 rounded-sm bg-signal px-3 py-1.5 text-sm font-semibold text-white hover:bg-ink"
        >
          Load forecast again
        </button>
      </div>
    )
  }

  return <ForecastView forecast={forecast.data} />
}
