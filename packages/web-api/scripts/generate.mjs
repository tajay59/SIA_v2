// Regenerate src/generated/<service>.ts from the OpenAPI contract.
//   npm run generate -w @cimh/web-api            (specs from docs/api by default)
//   SPEC_DIR=/path/to/docs/api npm run generate -w @cimh/web-api
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const pkg = resolve(here, '..')
const specDir = resolve(process.env.SPEC_DIR ?? join(pkg, '..', '..', 'docs', 'api'))
const outDir = join(pkg, 'src', 'generated')
const services = ['identity', 'catalog', 'inventory', 'orders', 'documents']
const bin = join(pkg, '..', '..', 'node_modules', '.bin', process.platform === 'win32' ? 'openapi-typescript.cmd' : 'openapi-typescript')

mkdirSync(outDir, { recursive: true })
for (const svc of services) {
  const spec = join(specDir, `${svc}.openapi.yaml`)
  if (!existsSync(spec)) throw new Error(`missing spec ${spec}`)
  execFileSync(bin, [spec, '-o', join(outDir, `${svc}.ts`)], { stdio: 'inherit', shell: process.platform === 'win32' })
}
console.log(`generated ${services.length} clients into ${outDir}`)
