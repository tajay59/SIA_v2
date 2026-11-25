// Dev only: put 500–1000 units of every active product on shelves, as if each had been stowed.
//
//   docker cp tools/perf/seed_stock_units.js sia-dev-mongo-1:/tmp/ && docker exec -e CONFIRM_DEV=1 sia-dev-mongo-1 mongosh --quiet inventory --file /tmp/seed_stock_units.js
//   (optional: -e MIN_UNITS=500 -e MAX_UNITS=1000 -e ACTOR=USR0001)
//
// Writes what inventory-svc's stow writes, in bulk: a `storage` unit per item (on a shelf, available), a `history`
// "stow" row per unit, then the product's `stock` recount with one `stock.changed` event in its outbox, so the
// outbox relay publishes it and catalog-consumer sets `inStock`. Units of one product spread over 1–4 random active
// shelves. Running it again adds another batch: it is a seeder, not a sync.
/* global db, process, print, ObjectId */

if (process.env.CONFIRM_DEV !== '1') {
  print('Refusing: set CONFIRM_DEV=1 (dev database only; never staging or production).')
  quit(1)
}
const MIN = Number(process.env.MIN_UNITS || 500)
const MAX = Number(process.env.MAX_UNITS || 1000)
const ACTOR = process.env.ACTOR || 'USR0001'
const BATCH = 5000

const CROCKFORD = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
function ulid() {
  let t = Date.now()
  let time = ''
  for (let i = 0; i < 10; i++) {
    time = CROCKFORD[t % 32] + time
    t = Math.floor(t / 32)
  }
  let rand = ''
  for (let i = 0; i < 16; i++) rand += CROCKFORD[Math.floor(Math.random() * 32)]
  return time + rand
}
const hex8 = () => Math.floor(Math.random() * 0x100000000).toString(16).padStart(8, '0')
const between = (a, b) => a + Math.floor(Math.random() * (b - a + 1))

// Places: shelf → site/location ids, names from their own records.
const names = {}
db.misc.find({ kind: { $in: ['site', 'location'] } }, { id: 1, name: 1 }).forEach((d) => (names[d.id] = d.name))
const shelves = db.misc
  .find({ kind: 'shelf', active: { $ne: false } }, { barcode: 1, number: 1, site: 1, location: 1 })
  .toArray()
  .map((s) => ({
    site: s.site,
    sitename: names[s.site] ?? null,
    location: s.location,
    locationname: names[s.location] ?? null,
    shelf: s.barcode,
    shelfnumber: s.number,
  }))
if (!shelves.length) {
  print('No active shelves: create some first.')
  quit(1)
}

const products = db.product.find({ active: { $ne: false } }, { id: 1 }).toArray().map((p) => p.id)
print(`${products.length} products, ${shelves.length} shelves, ${MIN}–${MAX} units each`)

const AVAILABLE = { stowed: true, picked: false, reservedFor: null }
const started = Date.now()
let units = 0
let dupes = 0
let pending = { storage: [], history: [] }

function flush() {
  if (pending.storage.length) {
    try {
      db.storage.insertMany(pending.storage, { ordered: false })
    } catch (e) {
      const failed = e.writeErrors?.length ?? e.result?.writeErrors?.length ?? 0
      if (!failed) throw e
      dupes += failed // a barcode collision: that unit is skipped (its history row stays harmless)
    }
    db.history.insertMany(pending.history, { ordered: false })
  }
  pending = { storage: [], history: [] }
}

function recount(pid) {
  const base = { product: pid }
  const counts = {
    available: db.storage.countDocuments({ ...base, ...AVAILABLE }),
    reserved: db.storage.countDocuments({ ...base, stowed: true, picked: false, reservedFor: { $gt: '' } }),
    picked: db.storage.countDocuments({ ...base, picked: true }),
    assigned: db.storage.countDocuments({ ...base, assignedTo: { $gt: '' } }),
  }
  const doc = db.stock.findOne({ id: pid }) || {}
  const threshold = Number(doc.threshold || 0)
  const active = doc.active !== false
  const low = active && threshold > 0 && counts.available <= threshold
  const event = {
    eventId: ulid(),
    type: 'stock.changed',
    version: 1,
    occurredAt: new Date(),
    correlationId: `seed-stock-${ulid()}`,
    actorId: ACTOR,
    payload: { productId: pid, available: counts.available, reserved: counts.reserved },
    attempts: 0,
  }
  db.stock.updateOne(
    { id: pid },
    { $set: { ...counts, low, updatedAt: new Date() }, $setOnInsert: { threshold: 0, active: true }, $push: { outbox: event } },
    { upsert: true },
  )
}

products.forEach((pid, i) => {
  const n = between(MIN, MAX)
  const spots = Array.from({ length: between(1, 4) }, () => shelves[Math.floor(Math.random() * shelves.length)])
  const t = new Date()
  for (let k = 0; k < n; k++) {
    const where = spots[k % spots.length]
    const barcode = `${pid}_${hex8()}`
    pending.storage.push({
      _id: new ObjectId(),
      barcode,
      product: pid,
      serial: null,
      stowed: true,
      picked: false,
      images: [],
      createdBy: ACTOR,
      createdAt: t,
      updatedAt: t,
      ...where,
      stowby: ACTOR,
      stowdate: t,
      pickedby: null,
      pickeddate: null,
      pickedreason: null,
    })
    pending.history.push({ id: barcode, operation: 'stow', user: ACTOR, date: t, site: where.site, location: where.location, shelf: where.shelf })
    if (pending.storage.length >= BATCH) flush()
  }
  flush() // this product's units are in before its recount
  recount(pid)
  units += n
  if ((i + 1) % 100 === 0 || i + 1 === products.length) {
    print(`${i + 1}/${products.length} products · ${units} units · ${Math.round((Date.now() - started) / 1000)} s`)
  }
})
print(`Done: ${units - dupes} units stowed (${dupes} barcode collisions skipped) in ${Math.round((Date.now() - started) / 1000)} s`)
