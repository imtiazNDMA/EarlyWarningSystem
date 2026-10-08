import type { Signal } from '../../api/client'

export type Level = Signal['level']

/** Lowest first. */
export const LEVELS: Level[] = ['moderate', 'severe', 'extreme']

export const LEVEL_LABELS: Record<Level, string> = {
  moderate: 'Moderate',
  severe: 'Severe',
  extreme: 'Extreme',
}

/**
 * Severity colours. These hues are reserved for hazard level and used nowhere
 * else in the interface; they always appear with the level's name beside them.
 */
export const LEVEL_COLOURS: Record<Level, string> = {
  moderate: '#F2C037',
  severe: '#E8730C',
  extreme: '#C8261B',
}

const HAZARD_LABELS: Record<string, string> = {
  heavy_rain: 'Heavy rain',
  heatwave: 'Heatwave',
  strong_wind: 'Strong wind',
  heavy_snow: 'Heavy snow',
}

export function hazardLabel(hazard: string): string {
  // An unknown hazard still reads sensibly: "dust_storm" -> "Dust storm"
  const fallback = hazard.replaceAll('_', ' ')
  return HAZARD_LABELS[hazard] ?? fallback.charAt(0).toUpperCase() + fallback.slice(1)
}

/** The highest level among the signals, or null when there are none. */
export function highestLevel(signals: Signal[]): Level | null {
  let highest = -1
  for (const signal of signals) {
    highest = Math.max(highest, LEVELS.indexOf(signal.level))
  }
  return highest === -1 ? null : LEVELS[highest]
}

/** Signals grouped by district, most severe first within each district. */
export function signalsByDistrict(signals: Signal[]): Map<string, Signal[]> {
  const groups = new Map<string, Signal[]>()
  for (const signal of signals) {
    groups.set(signal.district_id, [...(groups.get(signal.district_id) ?? []), signal])
  }
  for (const group of groups.values()) {
    group.sort((a, b) => LEVELS.indexOf(b.level) - LEVELS.indexOf(a.level))
  }
  return groups
}

/** One line for a tooltip: "Severe: heavy rain, strong wind". */
export function summarise(signals: Signal[]): string | null {
  const level = highestLevel(signals)
  if (level === null) return null
  const hazards = signals
    .filter((signal) => signal.level === level)
    .map((signal) => hazardLabel(signal.hazard).toLowerCase())
  return `${LEVEL_LABELS[level]}: ${hazards.join(', ')}`
}
