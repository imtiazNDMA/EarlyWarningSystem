import { describe, expect, it } from 'vitest'

import { formatDegreesMinutes } from './coordinates'

describe('formatDegreesMinutes', () => {
  it('formats a northern, eastern position as on a chart margin', () => {
    // Lahore: 0.4614° is 27.7′ and 0.3552° is 21.3′
    expect(formatDegreesMinutes(31.4614, 74.3552)).toBe('31°28′N 74°21′E')
  })

  it('uses S and W for negative values', () => {
    expect(formatDegreesMinutes(-33.5, -70.25)).toBe('33°30′S 70°15′W')
  })

  it('pads single-digit minutes', () => {
    expect(formatDegreesMinutes(24.05, 67.1)).toBe('24°03′N 67°06′E')
  })

  it('carries into the next degree when minutes round up to 60', () => {
    expect(formatDegreesMinutes(29.9999, 70.9999)).toBe('30°00′N 71°00′E')
  })
})
