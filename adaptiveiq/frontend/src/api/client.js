/** Fetch wrapper: same-origin cookies, the CSRF header the backend requires, readable errors. */
export class ApiError extends Error {
  constructor(status, message, body) {
    super(message)
    this.status = status
    this.body = body
  }
}

const BASE = import.meta.env.VITE_API_BASE || ''
let onUnauthorized = null
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

async function request(method, path, body, { raw } = {}) {
  let res
  try {
    res = await fetch(BASE + path, {
      method,
      credentials: 'include',
      headers: { 'X-Requested-With': 'AdaptiveIQ', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the AdaptiveIQ server. Check that the backend is running.')
  }
  if (raw && res.ok) return res
  if (res.status === 204) return null
  const text = await res.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    if (res.status === 401 && onUnauthorized && !path.startsWith('/api/auth/')) onUnauthorized()
    const detail = data && typeof data === 'object' ? data.detail : null
    const msg = typeof detail === 'string' ? detail : res.status >= 500 ? 'The server had a problem. Please try again.' : `Request failed (${res.status}).`
    throw new ApiError(res.status, msg, data)
  }
  return data
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b = {}) => request('POST', p, b),
  put: (p, b = {}) => request('PUT', p, b),
  patch: (p, b = {}) => request('PATCH', p, b),
  del: (p) => request('DELETE', p),
  text: async (p) => (await request('GET', p, undefined, { raw: true })).text(),
  /** Downloads a file from an authorised GET endpoint (CSV exports). */
  download: async (p, filename) => {
    const res = await request('GET', p, undefined, { raw: true })
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}

export function qs(params) {
  const s = new URLSearchParams()
  Object.entries(params || {}).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') s.set(k, v) })
  const out = s.toString()
  return out ? `?${out}` : ''
}
