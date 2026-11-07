/**
 * Catalogue API access and helpers shared by SHOP and SIA (catalog.openapi.yaml, DESIGN_BRIEF §9).
 * Customers only ever receive ProductPublic; staff get ProductStaff (cost, serials, version…).
 */
import { catalogClient, type CommonCatalogComponents } from '@cimh/web-api'
import { type ShallowRef, shallowRef } from 'vue'
import { call } from './api'

type S = CommonCatalogComponents['schemas']
export type ProductPublic = S['ProductPublic']
export type ProductStaff = S['ProductStaff']
export type Product = ProductPublic | ProductStaff
export type ProductInput = S['ProductInput']
export type ProductPatch = S['ProductPatch']
export type ProductType = S['ProductType']
export type ProductPhoto = S['Image']
export type Project = S['Project']
export type Fees = S['Fees']
export type EmailLists = S['EmailLists']
export type EmailListMember = S['EmailListMember']
export type WorkflowSettings = S['Settings']

export interface Reference {
  departments: string[]
  types: { key: ProductType; label: string }[]
  projects: Project[]
}

export const catalog = catalogClient()

export const PRODUCT_TYPES: ProductType[] = ['MET', 'RAD', 'EQUIP', 'SUPP', 'MISC', 'PRO']

export function isStaffProduct(p: Product): p is ProductStaff {
  return 'version' in p
}

export function primaryImage(p: Product): ProductPhoto | undefined {
  return p.images.find((i) => i.primary) ?? p.images[0]
}

/** media-worker writes <id>.webp (1600 px) plus <id>@800.webp and <id>@320.webp next to it. */
export function imageVariant(url: string, size: 800 | 320): string {
  return url.replace(/\.webp$/, `@${size}.webp`)
}

export function imageSrcset(url: string): string {
  return `${imageVariant(url, 320)} 320w, ${imageVariant(url, 800)} 800w, ${url} 1600w`
}

/** "Vaisala · WXT536" style line: make, model name and model number, whatever is present. */
export function makeModel(p: Product): string {
  return [p.make, p.modelname, p.modelnumber].filter(Boolean).join(' · ')
}

export function typeLabel(ref: Reference | null | undefined, key: string): string {
  return ref?.types.find((t) => t.key === key)?.label ?? key
}

/** Query-string booleans as the API expects them (absent = no filter). */
export function boolParam(v: unknown): boolean | undefined {
  if (v === true || v === 'true' || v === '1') return true
  if (v === false || v === 'false' || v === '0') return false
  return undefined
}

// ---- reference data: loaded once per page load, shared by every screen (it changes rarely).
let referencePromise: Promise<Reference> | null = null
const referenceRef = shallowRef<Reference | null>(null)

export function useReference(): { reference: ShallowRef<Reference | null>; reload: () => Promise<Reference> } {
  const reload = () => {
    referencePromise = call(() => catalog.GET('/reference')).then((r) => {
      referenceRef.value = r as Reference
      return r as Reference
    })
    referencePromise.catch(() => {
      referencePromise = null
    })
    return referencePromise
  }
  if (!referencePromise) void reload().catch(() => undefined)
  return { reference: referenceRef, reload }
}
