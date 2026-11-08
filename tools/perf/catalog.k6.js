// Catalogue read load test (TEST_STRATEGY §6 browse mix, catalogue part; IMPLEMENTATION_PLAN P3 exit).
//
//   MODE=steady RATE=50 DURATION=3m   constant arrival rate; gate p95 < 300 ms, p99 < 1 s, errors < 0.1 %
//   MODE=knee   MAX_RATE=400          ramp up to find where latency breaks (informational, no gate)
//
// Env: BASE (catalog API root), STAFF_TOKEN (optional Bearer for the staff share of the mix).
// Run with tools/perf/run_catalog.sh, which seeds, fetches a token and starts k6 in Docker.
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE || 'http://catalog-svc:8000/api/catalog/v1';
const MODE = __ENV.MODE || 'steady';
const RATE = Number(__ENV.RATE || 50);
const MAX_RATE = Number(__ENV.MAX_RATE || 400);
const STAFF = __ENV.STAFF_TOKEN ? { headers: { Authorization: `Bearer ${__ENV.STAFF_TOKEN}` } } : null;

const TYPES = ['MET', 'RAD', 'EQUIP', 'SUPP', 'MISC', 'PRO'];
const DEPARTMENTS = ['Meteorology', 'Radar', 'Climate', 'Hydrology', 'IT'];
const TERMS = ['Vaisala', 'anemometer', 'rain gauge', 'cable', 'barometer', 'magnetron', 'Campbell data logger',
  'solar panel', 'battery', 'pyranometer', 'Gill', 'thermometer', 'mast', 'connector', 'school weather kit'];

const ENDPOINTS = ['list', 'list_next', 'detail', 'search', 'staff_list', 'staff_search', 'staff_detail'];
const thresholds = {
  http_req_failed: ['rate<0.001'],
  checks: ['rate>0.999'],
};
if (MODE === 'steady') {
  thresholds.http_req_duration = ['p(95)<300', 'p(99)<1000'];
  for (const e of ENDPOINTS) thresholds[`http_req_duration{name:${e}}`] = ['p(95)<300'];
}

export const options = {
  scenarios: {
    browse: MODE === 'knee'
      ? {
        executor: 'ramping-arrival-rate', startRate: 10, timeUnit: '1s', preAllocatedVUs: 100, maxVUs: 600,
        stages: [{ target: MAX_RATE, duration: __ENV.DURATION || '4m' }],
      }
      : {
        executor: 'constant-arrival-rate', rate: RATE, timeUnit: '1s', duration: __ENV.DURATION || '3m',
        preAllocatedVUs: 50, maxVUs: 400,
      },
  },
  thresholds,
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

const pick = (a) => a[Math.floor(Math.random() * a.length)];
const q = (o) => Object.entries(o).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');

export function setup() {
  // Real product ids for detail requests: a few pages per type, public and staff.
  const pub = [];
  for (const t of TYPES) {
    const r = http.get(`${BASE}/products?${q({ type: t, limit: 100 })}`);
    pub.push(...r.json('items').map((p) => p.id));
  }
  if (pub.length === 0) throw new Error('no public products; seed first');
  return { ids: pub };
}

function filters() {
  const r = Math.random();
  if (r < 0.35) return {};
  if (r < 0.70) return { type: pick(TYPES) };
  if (r < 0.80) return { type: pick(TYPES), department: pick(DEPARTMENTS) };
  if (r < 0.90) return { probono: true };
  return { inStock: true };
}

function get(url, name, params) {
  const res = http.get(url, Object.assign({ tags: { name } }, params || {}));
  check(res, { [`${name} 200`]: (x) => x.status === 200 });
  return res;
}

export default function (data) {
  const r = Math.random();
  if (r < 0.35) {
    const res = get(`${BASE}/products?${q({ ...filters(), limit: 24 })}`, 'list');
    const next = res.status === 200 ? res.json('nextCursor') : null;
    if (next && Math.random() < 0.3) get(`${BASE}/products?${q({ limit: 24, cursor: next })}`, 'list_next');
  } else if (r < 0.60) {
    get(`${BASE}/products/${pick(data.ids)}`, 'detail');
  } else if (r < 0.85 || !STAFF) {
    get(`${BASE}/products/search?${q({ q: pick(TERMS), limit: 24 })}`, 'search');
  } else if (r < 0.92) {
    get(`${BASE}/products?${q({ ...filters(), includeInactive: Math.random() < 0.3, limit: 50 })}`, 'staff_list', STAFF);
  } else if (r < 0.97) {
    get(`${BASE}/products/search?${q({ q: pick(TERMS), limit: 50 })}`, 'staff_search', STAFF);
  } else {
    get(`${BASE}/products/${pick(data.ids)}`, 'staff_detail', STAFF);
  }
}
