import createClient from 'openapi-fetch'

import type { components, paths } from './schema'

/** Typed client for the backend; paths and payloads come from its OpenAPI schema. */
export const api = createClient<paths>({ baseUrl: '' })

export type District = components['schemas']['DistrictOut']
export type BoundaryProperties = components['schemas']['BoundaryProperties']
export type BoundaryCollection = components['schemas']['BoundaryCollection']
export type Forecast = components['schemas']['ForecastOut']
export type DailyForecast = components['schemas']['DailyForecast']
export type Signal = components['schemas']['SignalOut']
export type Run = components['schemas']['RunOut']
export type CurrentSignals = components['schemas']['CurrentSignals']
export type Alert = components['schemas']['AlertOut']
export type AlertDetail = components['schemas']['AlertDetail']
export type Evidence = components['schemas']['EvidenceOut']
