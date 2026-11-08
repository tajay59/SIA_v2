/** Save text as a file. The object URL is released right after the click. */
export function downloadText(text: string, filename: string, type = 'text/plain'): void {
  const blob = new Blob([text], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

/** Save a JSON body as a file (personal-data exports). */
export function downloadJson(body: unknown, filename: string): void {
  downloadText(JSON.stringify(body, null, 2), filename, 'application/json')
}

export function exportFilename(prefix: string, generatedAt: string): string {
  return `${prefix}-${generatedAt.slice(0, 10)}.json`
}
