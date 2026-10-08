import createClient from 'openapi-fetch'

import type { components, paths } from './schema'

/** Typed client for the backend; paths and payloads come from its OpenAPI schema. */
export const api = createClient<paths>({ baseUrl: '' })

export type District = components['schemas']['DistrictOut']
export type BoundaryProperties = components['schemas']['BoundaryProperties']
export type BoundaryCollection = components['schemas']['BoundaryCollection']
export type Forecast = components['schemas']['ForecastOut']
export type DailyForecast = components['schemas']['DailyForecast']
