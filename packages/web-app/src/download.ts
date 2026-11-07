/** Save a JSON body as a file (personal-data exports). The object URL is released right after the click. */
export function downloadJson(body: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(body, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

export function exportFilename(prefix: string, generatedAt: string): string {
  return `${prefix}-${generatedAt.slice(0, 10)}.json`
}
