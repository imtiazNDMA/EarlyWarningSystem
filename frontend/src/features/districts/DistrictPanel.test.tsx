import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { BoundaryProperties, District } from '../../api/client'
import { DistrictPanel } from './DistrictPanel'

const lahoreBoundary: BoundaryProperties = {
  feature_id: 'lahore',
  district_id: 'lahore',
  name_en: 'Lahore',
  province: 'Punjab',
}

const lahore: District = {
  id: 'lahore',
  name_en: 'Lahore',
  name_ur: null,
  province: 'Punjab',
  lat: 31.4614,
  lon: 74.3552,
  feature_id: 'lahore',
}

describe('DistrictPanel', () => {
  it('asks the user to pick a district when nothing is selected', () => {
    render(<DistrictPanel boundary={null} district={undefined} onClose={vi.fn()} />)

    expect(
      screen.getByText('Select a district on the map or from the list.'),
    ).toBeInTheDocument()
  })

  it('shows the selected district with its province and position', () => {
    render(
      <DistrictPanel boundary={lahoreBoundary} district={lahore} onClose={vi.fn()} />,
    )

    expect(screen.getByRole('heading', { name: 'Lahore' })).toBeInTheDocument()
    expect(screen.getByText('Punjab')).toBeInTheDocument()
    expect(screen.getByText('31°28′N 74°21′E')).toBeInTheDocument()
  })

  it('explains an area that has no district in the registry', () => {
    render(
      <DistrictPanel
        boundary={{
          feature_id: 'fr-bannu',
          district_id: null,
          name_en: 'FR BANNU',
          province: 'FATA',
        }}
        district={undefined}
        onClose={vi.fn()}
      />,
    )

    expect(screen.getByRole('heading', { name: 'FR BANNU' })).toBeInTheDocument()
    expect(
      screen.getByText('No forecasts or alerts are produced for this area.'),
    ).toBeInTheDocument()
  })

  it('clears the selection when closed', async () => {
    const onClose = vi.fn()
    render(
      <DistrictPanel boundary={lahoreBoundary} district={lahore} onClose={onClose} />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Clear selection' }))

    expect(onClose).toHaveBeenCalledOnce()
  })
})
