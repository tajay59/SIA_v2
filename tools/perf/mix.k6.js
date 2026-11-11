// TEST_STRATEGY §6 mixes on the dev stack (direct to the services, no edge). Fixture: setup_mix.py.
//
//   MODE=browse  60 % catalogue/search, 20 % product detail, 10 % my requests, 10 % login/refresh
//                gate p95 < 300 ms, p99 < 1 s, errors < 0.1 % (TR-PERF-1/3)
//   MODE=write   browse at RATE plus WRITE_RATE/s of cart updates, submissions, staff actions, scans
//                gate: writes p95 < 500 ms (TR-PERF-2); 409s from intended conflicts are not errors
//   MODE=burst   logins only, ramping to RATE/s (Argon2 cost); gate login p95 < 1 s
//   MODE=soak    browse + write at RATE for DURATION (8 h at sized-as-prod); same gates, watch memory and lag
//
// Env: RATE, WRITE_RATE, DURATION, FIXTURE (path inside the container). Local runs check that the mix works
// and where one dev container bends; the TR-PERF numbers are measured on production-sized hardware.
import http from 'k6/http';
import { check } from 'k6';

const MODE = __ENV.MODE || 'browse';
const RATE = Number(__ENV.RATE || 30);
const WRITE_RATE = Number(__ENV.WRITE_RATE || 5);
const DURATION = __ENV.DURATION || '3m';
const F = JSON.parse(open(__ENV.FIXTURE || '/perf/results/mix-fixture.json'));

const ID = 'http://identity-svc:8000/api/identity/v1';
const CAT = 'http://catalog-svc:8000/api/catalog/v1';
const INV = 'http://inventory-svc:8000/api/inventory/v1';
const ORD = 'http://order-svc:8000/api/orders/v1';
const TERMS = ['anemometer', 'rain gauge', 'barometer', 'Vaisala', 'cable', 'pyranometer', 'Perf mix'];

const arrival = (rate, exec) => ({
  executor: 'constant-arrival-rate', rate, timeUnit: '1s', duration: DURATION,
  preAllocatedVUs: Math.max(5, rate), maxVUs: Math.max(20, rate * 3), exec,
});
const scenarios = {};
const thresholds = { checks: ['rate>0.999'] };
if (MODE === 'browse' || MODE === 'write' || MODE === 'soak') {
  scenarios.browse = arrival(RATE, 'browse');
  thresholds['http_req_duration{kind:read}'] = ['p(95)<300', 'p(99)<1000'];
  thresholds['http_req_failed{kind:read}'] = ['rate<0.001'];
  // Sign-ins (each VU's first login, refreshes) have their own target (burst mode); 503 AUTH_BUSY under a
  // login storm is the designed overload answer.
  thresholds['http_req_duration{kind:auth}'] = ['p(95)<1000'];
}
if (MODE === 'write' || MODE === 'soak') {
  scenarios.write = arrival(WRITE_RATE, 'write');
  thresholds['http_req_duration{kind:write}'] = ['p(95)<500'];
}
if (MODE === 'burst') {
  scenarios.burst = {
    executor: 'ramping-arrival-rate', startRate: 1, timeUnit: '1s', exec: 'burst',
    preAllocatedVUs: 50, maxVUs: 400, stages: [{ target: RATE, duration: DURATION }],
  };
  thresholds['http_req_duration{name:login}'] = ['p(95)<1000'];
}
export const options = { scenarios, thresholds, summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'] };

// 401 (expired token, refreshed and retried) and 409 (intended conflicts) are expected answers, not failures.
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 399 }, 401, 409));

const pick = (a) => a[Math.floor(Math.random() * a.length)];
const uid = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;

// One session per VU, like one device: the VU logs in itself (several VUs may share a customer account, but
// never a refresh token: sharing one trips reuse detection, which revokes the family, as designed).
let me = null;
function session() {
  if (!me) {
    const c = F.customers[(__VU - 1) % F.customers.length];
    me = { email: c.email, password: c.password, access: '', refresh: '' };
    login(me);
  }
  return me;
}
let staffMe = null;
function staffSession() {
  if (!staffMe) {
    staffMe = { email: F.staff.email, password: F.staff.password, access: '', refresh: '' };
    login(staffMe);
  }
  return staffMe;
}
function auth(s) { return { Authorization: `Bearer ${s.access}` }; }
function refresh(s) {
  const r = http.post(`${ID}/auth/refresh`, JSON.stringify({ refreshToken: s.refresh }),
    { headers: { 'Content-Type': 'application/json' }, tags: { name: 'refresh', kind: 'auth' } });
  if (r.status === 200) { s.access = r.json('accessToken'); s.refresh = r.json('refreshToken'); return true; }
  return login(s);
}
function login(s) {
  const r = http.post(`${ID}/auth/login`, JSON.stringify({ email: s.email, password: s.password, client: 'mobile' }),
    { headers: { 'Content-Type': 'application/json' }, tags: { name: 'login', kind: 'auth' } });
  check(r, { 'login 200': (x) => x.status === 200 });
  if (r.status === 200) { s.access = r.json('accessToken'); s.refresh = r.json('refreshToken'); return true; }
  return false;
}
function call(method, url, body, name, kind, s, extra) {
  const params = { headers: Object.assign({ 'Content-Type': 'application/json' }, s ? auth(s) : {}, extra || {}),
    tags: { name, kind } };
  let r = http.request(method, url, body === null ? null : JSON.stringify(body), params);
  if (r.status === 401 && s && refresh(s)) {
    params.headers = Object.assign(params.headers, auth(s));
    r = http.request(method, url, body === null ? null : JSON.stringify(body), params);
  }
  return r;
}

export function browse() {
  const s = session();
  const r = Math.random();
  let res;
  if (r < 0.35) {
    res = call('GET', `${CAT}/products?limit=24`, null, 'catalogue', 'read');
  } else if (r < 0.60) {
    res = call('GET', `${CAT}/products/search?q=${encodeURIComponent(pick(TERMS))}&limit=24`, null, 'search', 'read');
  } else if (r < 0.80) {
    res = call('GET', `${CAT}/products/${pick(F.products)}`, null, 'detail', 'read');
  } else if (r < 0.90) {
    res = call('GET', `${ORD}/requests?limit=20`, null, 'my_requests', 'read', s);
  } else {
    check(null, { 'refresh ok': () => refresh(s) });
    return;
  }
  check(res, { [`${res.request ? 'read' : 'read'} 200`]: (x) => x.status === 200 });
}

export function write() {
  const s = session();
  const staff = staffSession();
  const r = Math.random();
  if (r < 0.40) {
    const res = call('PUT', `${ORD}/cart/lines/${pick(F.products)}`, { qty: 1 + Math.floor(Math.random() * 2) },
      'cart_update', 'write', s);
    check(res, { 'cart 200': (x) => x.status === 200 });
  } else if (r < 0.55) {
    call('PUT', `${ORD}/cart/lines/${pick(F.products)}`, { qty: 1 }, 'cart_update', 'write', s);
    const res = call('POST', `${ORD}/requests`, { currency: 'BBD', shipTo: { line1: 'Husbands', city: 'St James',
      country: 'BB', firstname: 'Perf', lastname: 'Mix', email: s.email } }, 'submit', 'write', s,
      { 'Idempotency-Key': uid() });
    check(res, { 'submit 201': (x) => x.status === 201 });
  } else if (r < 0.70) {
    // Staff: take the oldest submitted request into quoting. Two VUs may pick the same one: 409 is intended.
    const q = call('GET', `${ORD}/requests?status=SUBMITTED&limit=5`, null, 'staff_queue', 'read', staff);
    const items = q.status === 200 ? q.json('items') : [];
    if (items.length) {
      const it = pick(items);
      const res = call('POST', `${ORD}/requests/${it.id}/start-quoting`, null, 'start_quoting', 'write', staff,
        { 'If-Match': String(it.version) });
      check(res, { 'start-quoting 200/409': (x) => x.status === 200 || x.status === 409 });
    }
  } else {
    const res = call('POST', `${INV}/relocate`, { unit: pick(F.units), toShelf: pick(F.shelves) }, 'scan', 'write',
      staff, { 'Idempotency-Key': uid() });
    // 409 when the unit is already on that shelf or reserved: intended, not an error.
    check(res, { 'scan 200/409': (x) => x.status === 200 || x.status === 409 });
  }
}

export function burst() {
  login(Object.assign({}, pick(F.customers)));
}
