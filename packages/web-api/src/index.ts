/**
 * Typed fetch clients for each service, generated from the OpenAPI contract.
 *
 *   const orders = ordersClient()
 *   const { data, error } = await orders.GET('/requests/{requestId}', { params: { path: { requestId } } })
 *
 * Web clients use cookies + CSRF (API README §2): `credentials: 'include'` and the
 * X-CSRF-Token header echoed from the readable csrf_token cookie on unsafe methods.
 */
import createClient, { type Middleware } from 'openapi-fetch'
import type { paths as CatalogPaths } from './generated/catalog'
import type { paths as DocumentsPaths } from './generated/documents'
import type { paths as IdentityPaths } from './generated/identity'
import type { paths as InventoryPaths } from './generated/inventory'
import type { paths as OrdersPaths } from './generated/orders'

export const BASE = {
  identity: '/api/identity/v1',
  catalog: '/api/catalog/v1',
  inventory: '/api/inventory/v1',
  orders: '/api/orders/v1',
  documents: '/api/documents/v1',
} as const

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export function readCookie(name: string, cookieString: string = globalThis.document?.cookie ?? ''): string | undefined {
  for (const part of cookieString.split(';')) {
    const [k, ...v] = part.trim().split('=')
    if (k === name) return decodeURIComponent(v.join('='))
  }
  return undefined
}

export const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    if (UNSAFE.has(request.method)) {
      const token = readCookie('csrf_token')
      if (token) request.headers.set('X-CSRF-Token', token)
    }
    return request
  },
}

function make<P extends {}>(base: string, origin = '') {
  const client = createClient<P>({ baseUrl: origin + base, credentials: 'include' })
  client.use(csrfMiddleware)
  return client
}

export const identityClient = (origin?: string) => make<IdentityPaths>(BASE.identity, origin)
export const catalogClient = (origin?: string) => make<CatalogPaths>(BASE.catalog, origin)
export const inventoryClient = (origin?: string) => make<InventoryPaths>(BASE.inventory, origin)
export const ordersClient = (origin?: string) => make<OrdersPaths>(BASE.orders, origin)
export const documentsClient = (origin?: string) => make<DocumentsPaths>(BASE.documents, origin)

export type { CatalogPaths, DocumentsPaths, IdentityPaths, InventoryPaths, OrdersPaths }

export type { components as IdentityComponents } from './generated/identity'
export type { components as CommonCatalogComponents } from './generated/catalog'
