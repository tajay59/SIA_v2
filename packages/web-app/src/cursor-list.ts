/**
 * Cursor paging for list screens (API README §1: `cursor` + `limit`, response `nextCursor`).
 * "Load more" appends; changing filters calls `reload()`. Stale responses (filters changed while a
 * request was in flight) are dropped.
 */
import { ref, shallowRef } from 'vue'
import { useNotify } from './notify'

export interface Page<T> {
  items: T[]
  nextCursor?: string | null
}

export function useCursorList<T>(fetchPage: (cursor: string | undefined) => Promise<Page<T>>) {
  const items = shallowRef<T[]>([])
  const nextCursor = ref<string | null>(null)
  const loading = ref(false)
  const loaded = ref(false)
  const failed = ref(false)
  let generation = 0

  async function run(cursor: string | undefined, append: boolean) {
    const gen = ++generation
    loading.value = true
    failed.value = false
    try {
      const page = await fetchPage(cursor)
      if (gen !== generation) return
      items.value = append ? [...items.value, ...page.items] : page.items
      nextCursor.value = page.nextCursor ?? null
      loaded.value = true
    } catch (e) {
      if (gen !== generation) return
      failed.value = true
      useNotify().report(e, { retry: () => void run(cursor, append) })
    } finally {
      if (gen === generation) loading.value = false
    }
  }

  return {
    items,
    nextCursor,
    loading,
    loaded,
    failed,
    reload: () => run(undefined, false),
    loadMore: () => (nextCursor.value ? run(nextCursor.value, true) : Promise.resolve()),
  }
}
