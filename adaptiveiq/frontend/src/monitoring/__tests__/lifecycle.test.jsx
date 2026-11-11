import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { useMonitoring } from '../useMonitoring'
import { studentApi } from '../../api/endpoints'

vi.mock('../../api/endpoints', () => ({ studentApi: {
  myMonitoring: vi.fn(), monitoringEvents: vi.fn(), monitoringDevices: vi.fn(),
} }))
const attempt = { monitoring: { tab: true, fullscreen: 'off', camera: false, microphone: false } }
const events = () => studentApi.monitoringEvents.mock.calls.flatMap(([id, batch]) => batch)
beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  studentApi.myMonitoring.mockResolvedValue({ events: [] })
  studentApi.monitoringEvents.mockResolvedValue({})
  studentApi.monitoringDevices.mockResolvedValue({})
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('does not reuse sequence numbers when the server record cannot be loaded', async () => {
  studentApi.myMonitoring.mockRejectedValue(new Error('offline'))
  const { result } = renderHook(() => useMonitoring({ attempt, sessionId: 11 }))
  await act(async () => { await result.current.start() })
  expect(result.current.started).toBe(false)
  expect(result.current.notice).toContain('Reconnect and reload')
  expect(studentApi.monitoringEvents).not.toHaveBeenCalled()
})

it('keeps startup synchronization when the same attempt is fetched again', async () => {
  let resolveRecord
  studentApi.myMonitoring.mockImplementation(() => new Promise((resolve) => { resolveRecord = resolve }))
  const { result, rerender } = renderHook(({ value }) => useMonitoring({ attempt: value, sessionId: 13 }), {
    initialProps: { value: attempt },
  })
  let startup
  act(() => { startup = result.current.start() })
  rerender({ value: { monitoring: { ...attempt.monitoring } } })
  await act(async () => { resolveRecord({ events: [{ seq: 7 }] }); await startup })
  expect(studentApi.myMonitoring).toHaveBeenCalledOnce()
  expect(result.current.started).toBe(true)
  expect(events()[0].seq).toBe(8)
  await act(async () => { await result.current.finish() })
})

it('records fullscreen transitions once and removes the listener at finish', async () => {
  let fullscreen = null
  Object.defineProperty(document, 'fullscreenEnabled', { configurable: true, value: true })
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, get: () => fullscreen })
  document.documentElement.requestFullscreen = vi.fn(async () => {
    fullscreen = document.documentElement
    document.dispatchEvent(new Event('fullscreenchange'))
  })
  document.exitFullscreen = vi.fn(async () => {
    fullscreen = null
    document.dispatchEvent(new Event('fullscreenchange'))
  })
  const watched = { monitoring: { ...attempt.monitoring, fullscreen: 'required' } }
  const { result } = renderHook(() => useMonitoring({ attempt: watched, sessionId: 12 }))
  await act(async () => { await result.current.start() })
  act(() => document.dispatchEvent(new Event('fullscreenchange')))
  await act(async () => { await document.exitFullscreen() })
  expect(result.current.needsFullscreen).toBe(true)
  await act(async () => { await result.current.finish() })
  expect(events().filter((e) => e.kind === 'fullscreen_enter')).toHaveLength(1)
  expect(events().filter((e) => e.kind === 'fullscreen_exit')).toHaveLength(1)
  delete document.fullscreenEnabled
  delete document.fullscreenElement
  delete document.documentElement.requestFullscreen
  delete document.exitFullscreen
})

it('combines blur and hidden into one departure and removes listeners at finish', async () => {
  const { result } = renderHook(() => useMonitoring({ attempt, sessionId: 8 }))
  await act(async () => { await result.current.start() })
  act(() => {
    window.dispatchEvent(new Event('blur'))
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
    window.dispatchEvent(new Event('focus'))
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await act(async () => { await result.current.finish() })
  expect(events().filter((e) => e.kind === 'page_hidden')).toHaveLength(1)
  expect(events().filter((e) => e.kind === 'page_visible')).toHaveLength(1)
  const count = events().length
  window.dispatchEvent(new Event('blur'))
  expect(events()).toHaveLength(count)
})

it('stops a camera permission result arriving after unmount without requesting microphone', async () => {
  let grant
  const stop = vi.fn()
  const getUserMedia = vi.fn(() => new Promise((resolve) => { grant = resolve }))
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } })
  const watched = { monitoring: { ...attempt.monitoring, camera: true, microphone: true } }
  const { result, unmount } = renderHook(() => useMonitoring({ attempt: watched, sessionId: 9 }))
  let starting
  act(() => { starting = result.current.start() })
  await waitFor(() => expect(getUserMedia).toHaveBeenCalledOnce())
  unmount()
  await act(async () => { grant({ getTracks: () => [{ stop }] }); await starting })
  expect(stop).toHaveBeenCalledOnce()
  expect(getUserMedia).toHaveBeenCalledOnce()
  expect(studentApi.monitoringDevices).not.toHaveBeenCalled()
})

it('releases the microphone when Web Audio setup fails', async () => {
  const stop = vi.fn()
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }) } })
  vi.stubGlobal('AudioContext', class { constructor() { throw new Error('unavailable') } })
  const watched = { monitoring: { ...attempt.monitoring, microphone: true } }
  const { result } = renderHook(() => useMonitoring({ attempt: watched, sessionId: 10 }))
  await act(async () => { await result.current.start() })
  expect(stop).toHaveBeenCalled()
  expect(result.current.devices.microphone).toBe('unavailable')
  await act(async () => { await result.current.finish() })
})

it('tags window blur separately from tab hidden and reports unavailable detector load', async () => {
  const stop = vi.fn()
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }], getVideoTracks: () => [{}] }) } })
  const watched = { monitoring: { ...attempt.monitoring, camera: true } }
  const loadDetector = vi.fn().mockRejectedValue(new Error('wasm failed'))
  const { result } = renderHook(() => useMonitoring({ attempt: watched, sessionId: 14, loadDetector }))
  await act(async () => { await result.current.start() })
  await waitFor(() => expect(studentApi.monitoringDevices).toHaveBeenLastCalledWith(14, { camera: 'unavailable', microphone: 'not_requested' }))
  expect(result.current.devices.camera).toBe('unavailable')
  act(() => {
    window.dispatchEvent(new Event('blur'))
    window.dispatchEvent(new Event('focus'))
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await act(async () => { await result.current.finish() })
  const hidden = events().filter((e) => e.kind === 'page_hidden')
  expect(hidden.map((e) => e.details.reason)).toEqual(['window_blur', 'tab_hidden'])
  expect(events().some((e) => e.kind === 'camera_lost')).toBe(true)
})
