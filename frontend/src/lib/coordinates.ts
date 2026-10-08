function degreesMinutes(value: number, positive: string, negative: string): string {
  const totalMinutes = Math.round(Math.abs(value) * 60)
  const degrees = Math.floor(totalMinutes / 60)
  const minutes = String(totalMinutes % 60).padStart(2, '0')
  return `${degrees}°${minutes}′${value < 0 ? negative : positive}`
}

/** Format a position in degrees and minutes, the way chart margins print it. */
export function formatDegreesMinutes(lat: number, lon: number): string {
  return `${degreesMinutes(lat, 'N', 'S')} ${degreesMinutes(lon, 'E', 'W')}`
}
