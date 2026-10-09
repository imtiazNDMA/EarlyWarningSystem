import type { Alert } from '../../api/client'
import { LEVELS, type Level } from '../signals/signals'

// The one hazard that is not weather; it has a map layer of its own
const AIR_QUALITY_HAZARD = 'poor_air_quality'

export function weatherAlerts(alerts: Alert[]): Alert[] {
  return alerts.filter((alert) => alert.hazard !== AIR_QUALITY_HAZARD)
}

export function airQualityAlerts(alerts: Alert[]): Alert[] {
  return alerts.filter((alert) => alert.hazard === AIR_QUALITY_HAZARD)
}

/** Active alerts grouped by district, most severe first within each district. */
export function alertsByDistrict(alerts: Alert[]): Map<string, Alert[]> {
  const groups = new Map<string, Alert[]>()
  for (const alert of alerts) {
    groups.set(alert.district_id, [...(groups.get(alert.district_id) ?? []), alert])
  }
  for (const group of groups.values()) {
    group.sort((a, b) => LEVELS.indexOf(b.severity) - LEVELS.indexOf(a.severity))
  }
  return groups
}

export function highestAlertLevel(alerts: Alert[]): Level | null {
  let highest = -1
  for (const alert of alerts) {
    highest = Math.max(highest, LEVELS.indexOf(alert.severity))
  }
  return highest === -1 ? null : LEVELS[highest]
}

/** One line for a map tooltip: "Severe: heavy rain, strong wind". */
export function summariseAlerts(alerts: Alert[]): string | null {
  const level = highestAlertLevel(alerts)
  if (level === null) return null
  const hazards = alerts
    .filter((alert) => alert.severity === level)
    .map((alert) => alert.hazard.replaceAll('_', ' '))
  return `${level.charAt(0).toUpperCase() + level.slice(1)}: ${hazards.join(', ')}`
}
