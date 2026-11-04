const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, options);
  } catch {
    throw new Error('Could not reach the API. Is the backend running?');
  }

  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return body;
}

export function getDataset(datasetId) {
  return request(`/api/datasets/${datasetId}`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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
