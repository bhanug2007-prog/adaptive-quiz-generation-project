import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, qs, setUnauthorizedHandler } from '../client'

const reply = (status, body) => Promise.resolve(new Response(body === undefined ? null : JSON.stringify(body), { status }))

afterEach(() => { vi.restoreAllMocks(); setUnauthorizedHandler(null) })

describe('api client', () => {
  it('sends cookies and the CSRF header, and JSON bodies', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockReturnValue(reply(200, { ok: true }))
    await api.post('/api/x', { a: 1 })
    const [, init] = f.mock.calls[0]
    expect(init.credentials).toBe('include')
    expect(init.headers['X-Requested-With']).toBe('AdaptiveIQ')
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(init.body).toBe('{"a":1}')
  })

  it('turns the backend detail into the error message', async () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(reply(422, { detail: 'Approve every question first.' }))
    await expect(api.post('/api/x')).rejects.toMatchObject({ status: 422, message: 'Approve every question first.' })
  })

  it('gives a readable message when the server cannot be reached', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const e = await api.get('/api/x').catch((x) => x)
    expect(e).toBeInstanceOf(ApiError)
    expect(e.status).toBe(0)
    expect(e.message).toMatch(/Cannot reach/)
  })

  it('calls the sign-out handler on 401, except for auth endpoints', async () => {
    const onOut = vi.fn()
    setUnauthorizedHandler(onOut)
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => reply(401, { detail: 'Please sign in.' }))
    await api.get('/api/student/overview').catch(() => {})
    await api.get('/api/auth/me').catch(() => {})
    expect(onOut).toHaveBeenCalledTimes(1)
  })

  it('hides server internals on 500', async () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(reply(500, { detail: { trace: 'secret' } }))
    await expect(api.get('/api/x')).rejects.toMatchObject({ message: 'The server had a problem. Please try again.' })
  })

  it('builds query strings without empty values', () => {
    expect(qs({ a: 1, b: '', c: null, d: undefined, e: 'x y' })).toBe('?a=1&e=x+y')
    expect(qs({})).toBe('')
  })
})
