/** Shapes from docs/api/common.yaml that the generated identity types reference but don't name. */
export interface ShippingAddress {
  line1: string
  line2?: string | null
  city: string
  parish?: string | null
  country: string
  zip?: string | null
  organisation?: string | null
  attention?: string | null
  firstname: string
  lastname: string
  email: string
  tel?: string | null
}
