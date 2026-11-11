import { expect, it, vi } from 'vitest'
import { createSpeechWarningGate, createWarningTracker } from '../warnings'
import { createVad } from '../detectors'

const policy = { cooldown_ms: 15000, persistence_ms: { face_multiple: 3000, face_none: 10000, speech: 5000, page_hidden: 1000, fullscreen_exit: 1000 } }
const storage = () => { const m = new Map(); return { getItem: (k) => m.get(k), setItem: (k, v) => m.set(k, v) } }

it('counts an ongoing multiple-face episode once across refresh and cooldown', () => {
  const store = storage(), emit = vi.fn()
  let tracker = createWarningTracker(1, policy, emit, { storage: store })
  for (let t = 0; t <= 20000; t += 1500) tracker.sample('face_multiple', true, t)
  expect(emit).toHaveBeenCalledTimes(1)
  tracker = createWarningTracker(1, policy, emit, { storage: store })
  tracker.sample('face_multiple', true, 30000)
  expect(emit).toHaveBeenCalledTimes(1)
  tracker.sample('face_multiple', false, 31000)
  tracker.sample('face_multiple', true, 31500) // one bad frame does not rearm
  tracker.sample('face_multiple', false, 32000)
  tracker.sample('face_multiple', false, 33500)
  tracker.sample('face_multiple', true, 35000)
  tracker.sample('face_multiple', true, 38000)
  expect(emit).toHaveBeenCalledTimes(2)
  expect(emit.mock.calls[0][1].details.incident_id).not.toBe(emit.mock.calls[1][1].details.incident_id)
})

it('requires sustained absence and does not promote unobserved refresh time', () => {
  const store = storage(), emit = vi.fn()
  let tracker = createWarningTracker(2, policy, emit, { storage: store })
  tracker.sample('face_none', true, 0)
  tracker.sample('face_none', true, 9000)
  tracker = createWarningTracker(2, policy, emit, { storage: store })
  tracker.sample('face_none', true, 50000)
  expect(emit).not.toHaveBeenCalled()
  tracker.sample('face_none', true, 60000)
  expect(emit).toHaveBeenCalledTimes(1)
})

it('does not count time when camera samples were unavailable', () => {
  const emit = vi.fn(), tracker = createWarningTracker(5, policy, emit, { storage: storage() })
  tracker.sample('face_none', true, 0)
  tracker.sample('face_none', true, 9000)
  tracker.pause('face_none')
  tracker.sample('face_none', true, 50000)
  expect(emit).not.toHaveBeenCalled()
  tracker.sample('face_none', true, 60000)
  expect(emit).toHaveBeenCalledTimes(1)
  tracker.pause('face_none')
  tracker.sample('face_none', true, 80000)
  expect(emit).toHaveBeenCalledTimes(1)
})

it.each(['page_hidden', 'fullscreen_exit'])('debounces and counts one %s incident', (signal) => {
  const emit = vi.fn(), tracker = createWarningTracker(3, policy, emit, { storage: storage() })
  tracker.sample(signal, true, 0)
  tracker.sample(signal, false, 500)
  tracker.sample(signal, false, 1500)
  expect(emit).not.toHaveBeenCalled()
  tracker.sample(signal, true, 2000)
  tracker.sample(signal, true, 3000)
  tracker.sample(signal, true, 10000)
  tracker.sample(signal, false, 11000)
  tracker.sample(signal, false, 12000)
  tracker.sample(signal, true, 13000)
  tracker.sample(signal, true, 14000)
  tracker.sample(signal, true, 30000) // suppressed incident stays suppressed
  expect(emit).toHaveBeenCalledTimes(1)
})

it('ignores background fan, clicks and quiet sound but warns once for sustained modulated sound', () => {
  const run = (levels) => {
    const emit = vi.fn(), tracker = createWarningTracker(4, policy, emit, { storage: storage() })
    const vad = createVad(), gate = createSpeechWarningGate()
    levels.forEach((level, i) => { vad.push(level, i * 100); tracker.sample('speech', vad.active, i * 100, {}, gate(level, vad.active, i * 100)) })
    return emit
  }
  const quiet = Array(30).fill(-70)
  expect(run([...quiet, ...Array(600).fill(-40)])).not.toHaveBeenCalled()
  expect(run([...quiet, -20, -20, ...quiet])).not.toHaveBeenCalled()
  expect(run(Array(100).fill(-60))).not.toHaveBeenCalled()
  const phrase = [...Array(25).fill(-25), ...Array(5).fill(-70)]
  expect(run([...quiet, ...Array(10).fill(phrase).flat(), ...quiet])).toHaveBeenCalledTimes(1)
})

it('does not rearm a speech warning while the same VAD episode remains active', () => {
  const emit = vi.fn(), tracker = createWarningTracker(6, policy, emit, { storage: storage() })
  tracker.sample('speech', true, 0)
  tracker.sample('speech', true, 5000)
  tracker.sample('speech', true, 30000, {}, false)
  tracker.sample('speech', true, 40000, {}, false)
  tracker.sample('speech', true, 50000)
  tracker.sample('speech', true, 60000)
  expect(emit).toHaveBeenCalledTimes(1)
})
