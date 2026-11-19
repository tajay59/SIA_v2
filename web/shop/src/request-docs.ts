/**
 * How a request's files are named where several sit side by side (View and sign's quote tabs, S-12 step 1).
 */
import { FILE_KIND_LABELS, type FileRef } from '@cimh/web-app'

/**
 * A tab's name, kept short (the file name is the tab's tooltip): what it is, numbered when there are several of a
 * kind ("Supplier quote 2"; S-12 passes the supplier's name instead), generated files their quote version when a
 * revision left more than one ("Agreement v2").
 */
export function docLabel(f: FileRef, all: FileRef[]): string {
  const kind = FILE_KIND_LABELS[f.kind]
  if (f.kind === 'supplier_quote' || f.kind === 'upload') {
    const same = all.filter((g) => g.kind === f.kind)
    return same.length > 1 ? `${kind} ${same.indexOf(f) + 1}` : kind
  }
  const twins = all.filter((g) => g.kind === f.kind).length > 1
  return twins && f.quoteVersion ? `${kind} v${f.quoteVersion}` : kind
}
