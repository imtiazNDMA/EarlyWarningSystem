import { useMemo } from 'react'

import type { District } from '../../api/client'

type Props = {
  districts: District[]
  /** feature_id of the selected district, or null. */
  selectedFeatureId: string | null
  onSelect: (district: District) => void
}

/** Keyboard-reachable way to select a district, grouped by province. */
export function DistrictPicker({ districts, selectedFeatureId, onSelect }: Props) {
  const byProvince = useMemo(() => {
    const groups = new Map<string, District[]>()
    for (const district of districts) {
      groups.set(district.province, [...(groups.get(district.province) ?? []), district])
    }
    return [...groups.entries()]
  }, [districts])

  const selected = districts.find((d) => d.feature_id === selectedFeatureId)

  return (
    <label className="mt-3 block">
      <span className="type-label text-ink/60">Find a district</span>
      <select
        className="mt-1 block w-full rounded-sm border border-line/50 bg-white px-2 py-1.5 text-sm text-ink"
        value={selected?.id ?? ''}
        onChange={(event) => {
          const district = districts.find((d) => d.id === event.target.value)
          if (district) onSelect(district)
        }}
      >
        <option value="" disabled>
          Choose from {districts.length} districts
        </option>
        {byProvince.map(([province, provinceDistricts]) => (
          <optgroup key={province} label={province}>
            {provinceDistricts.map((district) => (
              <option key={district.id} value={district.id}>
                {district.name_en}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </label>
  )
}
