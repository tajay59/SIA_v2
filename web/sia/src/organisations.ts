/** Organisation types (identity `Organisation.type`) with their display names; shared by A-18 list and record. */
export const ORG_TYPES = [
  { value: 'met_service', title: 'Meteorological service' },
  { value: 'hydro_service', title: 'Hydrological service' },
  { value: 'government', title: 'Government' },
  { value: 'academic', title: 'Academic' },
  { value: 'other', title: 'Other' },
] as const
export const orgTypeTitle = (t?: string | null) => ORG_TYPES.find((x) => x.value === t)?.title ?? '—'
