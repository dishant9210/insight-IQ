// Empty = same origin: the gateway serves the app and proxies /api, which is
// what lets the refresh cookie be first-party. Set VITE_API_URL only to call
// an api on another origin (sign-in then won't survive a reload).
const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

// The access token lives in memory only, never in localStorage, so a script
// injected into the page can't read a long-lived credential. On reload the
// httpOnly refresh cookie gets a new one.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let session = null;            // { token, user }
const listeners = new Set();

// Not a credential: just whether to try restoring a session on load, so
// guests don't make a refresh call that's bound to fail.
const HINT = 'iq_signed_in';

function setSession(next) {
  session = next;
  try {
    if (next) localStorage.setItem(HINT, '1');
    else localStorage.removeItem(HINT);
  } catch { /* storage blocked: we just try the refresh every time */ }
  listeners.forEach((fn) => fn(session?.user ?? null));
}

export function onUserChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

async function send(path, options = {}) {
  const headers = { ...options.headers };
  if (session) headers.Authorization = `Bearer ${session.token}`;
  try {
    return await fetch(`${API_URL}${path}`, { ...options, headers, credentials: 'include' });
  } catch {
    throw new Error('Could not reach the API. Is the backend running?');
  }
}

async function parse(res) {
  if (res.status === 204) return null;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : `Request failed (${res.status})`;
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return body;
}

async function request(path, options = {}) {
  let res = await send(path, options);
  // access tokens are short-lived: refresh once and retry
  if (res.status === 401 && session) {
    if (await refreshSession()) res = await send(path, options);
    else throw Object.assign(new Error('Your session ended. Sign in again.'), { status: 401 });
  }
  return parse(res);
}

// --- accounts ---------------------------------------------------------------

const json = (body) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

async function startSession(path, body) {
  const data = await parse(await send(path, json(body)));
  setSession({ token: data.access_token, user: data.user });
  return data.user;
}

export const register = (email, password) => startSession('/api/auth/register', { email, password });
export const login = (email, password) => startSession('/api/auth/login', { email, password });

let refreshing = null;

// One refresh at a time per tab. Another tab may have just used the same
// cookie; the server tolerates that briefly, so a single retry picks up the
// cookie that tab got back.
export function refreshSession() {
  refreshing ??= (async () => {
    for (let attempt = 0; attempt < 2; attempt++) {
      const res = await fetch(`${API_URL}/api/auth/refresh`, { method: 'POST', credentials: 'include' })
        .catch(() => null);
      if (res?.ok) {
        const data = await res.json();
        setSession({ token: data.access_token, user: data.user });
        return true;
      }
      if (!res || res.status === 429) break;
      await sleep(400);
    }
    setSession(null);
    return false;
  })().finally(() => { refreshing = null; });
  return refreshing;
}

export function restoreSession() {
  let hinted = true;
  try { hinted = localStorage.getItem(HINT) === '1'; } catch { /* unknown: try */ }
  return hinted ? refreshSession() : Promise.resolve(false);
}

export async function logout() {
  await fetch(`${API_URL}/api/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => {});
  setSession(null);
}

// --- history ----------------------------------------------------------------

export function getHistory({ before, datasetId, limit = 20 } = {}) {
  const params = new URLSearchParams({ limit });
  if (before) params.set('before', before);
  if (datasetId) params.set('dataset_id', datasetId);
  return request(`/api/queries?${params}`);
}

export const getPastAnswer = (queryId) => request(`/api/queries/${queryId}`);
export const listDatasets = () => request('/api/datasets');
export const deleteDataset = (datasetId) => request(`/api/datasets/${datasetId}`, { method: 'DELETE' });

export function getDataset(datasetId) {
  return request(`/api/datasets/${datasetId}`);
}


// Large files are parsed by a background worker: the upload returns straight
// away with status "pending", so poll until it is ready or failed.
export async function uploadDataset(file, { onStatus, timeoutMs = 5 * 60 * 1000 } = {}) {
  const form = new FormData();
  form.append('file', file);
  let data = await request('/api/upload', { method: 'POST', body: form });

  const started = Date.now();
  while (data.status === 'pending' || data.status === 'processing') {
    onStatus?.(data.status);
    if (Date.now() - started > timeoutMs) {
      throw new Error('Processing is taking too long. Try again later.');
    }
    await sleep(1000);
    data = await getDataset(data.dataset_id);
  }
  if (data.status === 'failed') throw new Error(data.error || 'Could not process this file');
  return data;
}

export function queryDataset(datasetId, question) {
  return request('/api/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dataset_id: datasetId, question }),
  });
}

export function sendFeedback(queryId, helpful) {
  return request(`/api/queries/${queryId}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ helpful }),
  });
}

// notes: { table: { column: "what this column means" } }
export function saveDictionary(datasetId, notes) {
  return request(`/api/datasets/${datasetId}/dictionary`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tables: notes }),
  });
}
