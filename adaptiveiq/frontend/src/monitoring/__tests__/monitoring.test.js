// Phase 6: the pure detectors and the event queue behind integrity monitoring.
import { describe, expect, it, vi } from 'vitest'
import { createFaceTracker, createVad, rmsDb } from '../detectors'
import { createEventQueue } from '../eventQueue'

function memStorage() {
  const m = new Map()
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) }
}

describe('rmsDb', () => {
  it('gives -100 for silence and about -3 dB for a full-scale sine', () => {
    expect(rmsDb(new Float32Array(100))).toBe(-100)
    const sine = Float32Array.from({ length: 1000 }, (_, i) => Math.sin((2 * Math.PI * i) / 50))
    expect(rmsDb(sine)).toBeCloseTo(-3.01, 1)
  })
})

describe('voice activity detection', () => {
  const run = (frames, opts) => {
    const vad = createVad(opts)
    const out = []
    frames.forEach((lvl, i) => { const s = vad.push(lvl, i * 100); if (s) out.push(s) })
    const last = vad.flush(frames.length * 100)
    if (last) out.push(last)
    return out
  }
  const quiet = (n) => Array(n).fill(-70)
  const loud = (n) => Array(n).fill(-25)

  it('reports a stretch of sound well above the background with its length', () => {
    const segs = run([...quiet(30), ...loud(25), ...quiet(30)])
    expect(segs).toEqual([{ start: 3000, end: 5400 }])
  })
  it('ignores short noises like a click or a cough', () => {
    expect(run([...quiet(30), ...loud(2), ...quiet(30)])).toEqual([])
    expect(run([...quiet(30), ...loud(8), ...quiet(30)])).toEqual([])          // 0.8 s is under the 1 s report minimum
  })
  it('keeps reporting a long conversation with natural pauses', () => {
    const sentence = [...loud(25), ...quiet(5)]                                   // 2.5 s talk, 0.5 s pause
    const segs = run([...quiet(30), ...Array(10).fill(sentence).flat(), ...quiet(30)])
    expect(segs).toHaveLength(1)
    expect(segs[0].end - segs[0].start).toBeGreaterThanOrEqual(25000)            // 30 s of talk stays one long segment
  })
  it('keeps one segment across short pauses between words', () => {
    const talk = [...loud(10), ...quiet(4), ...loud(10), ...quiet(4), ...loud(10)]
    const segs = run([...quiet(30), ...talk, ...quiet(30)])
    expect(segs).toHaveLength(1)
    expect(segs[0].end - segs[0].start).toBe(3700)
  })
  it('adapts to a steady background such as a fan instead of reporting it forever', () => {
    const fan = Array(600).fill(-40)                                              // 60 s of steady noise
    const segs = run([...quiet(30), ...fan])
    const total = segs.reduce((a, s) => a + s.end - s.start, 0)
    expect(total).toBeLessThan(10000)                                             // under the 10 s "prolonged" mark
    const vad = createVad()
    ;[...quiet(30), ...fan].forEach((l, i) => vad.push(l, i * 100))
    expect(vad.noiseDb).toBeGreaterThan(-60)                                      // the background moved up towards the fan
  })
  it('never fires below the absolute floor, however quiet the room', () => {
    expect(run([...Array(30).fill(-95), ...Array(30).fill(-60), ...Array(30).fill(-95)])).toEqual([])
  })
})

describe('face tracker', () => {
  const feed = (counts, confirm = 2) => {
    const t = createFaceTracker({ confirm })
    const out = []
    counts.forEach((n, i) => { const e = t.push(n, i * 1000); if (e) out.push(e) })
    const last = t.flush(counts.length * 1000)
    if (last) out.push(last)
    return out
  }
  it('ignores a single frame without a face', () => {
    expect(feed([1, 1, 0, 1, 1])).toEqual([])
  })
  it('reports no face from the first missing frame until a face returns', () => {
    expect(feed([1, 0, 0, 0, 1, 1])).toEqual([{ kind: 'face_none', start: 1000, end: 4000, faces: 0 }])
  })
  it('reports several faces with the most seen', () => {
    expect(feed([1, 2, 3, 2, 1])).toEqual([{ kind: 'face_multiple', start: 1000, end: 4000, faces: 3 }])
  })
  it('switches straight from several faces to none', () => {
    expect(feed([2, 2, 0, 0, 1]).map((e) => e.kind)).toEqual(['face_multiple', 'face_none'])
  })
  it('closes an open episode when monitoring stops', () => {
    expect(feed([1, 0, 0, 0])).toEqual([{ kind: 'face_none', start: 1000, end: 4000, faces: 0 }])
  })
})

describe('event queue', () => {
  it('numbers events, sends them in batches and empties when accepted', async () => {
    const sent = []
    const q = createEventQueue(7, async (ev) => { sent.push(ev) }, { storage: memStorage(), batch: 2 })
    q.add('page_hidden'); q.add('page_visible', { duration_ms: 1200 }); q.add('speech', { duration_ms: 3000 })
    expect(await q.flush()).toBe(true)
    expect(sent.map((b) => b.map((e) => e.seq))).toEqual([[1, 2], [3]])
    expect(sent[0][1]).toMatchObject({ kind: 'page_visible', duration_ms: 1200 })
    expect(q.pending).toBe(0)
  })
  it('keeps events while offline and sends them later, after a reload too', async () => {
    const storage = memStorage()
    const down = vi.fn().mockRejectedValue(Object.assign(new Error('offline'), { status: 0 }))
    const q = createEventQueue(9, down, { storage })
    q.add('page_hidden'); q.add('page_visible')
    expect(await q.flush()).toBe(false)
    expect(q.pending).toBe(2)
    const sent = []
    const again = createEventQueue(9, async (ev) => { sent.push(...ev) }, { storage })         // page reloaded
    again.add('fullscreen_exit')
    await again.flush()
    expect(sent.map((e) => e.seq)).toEqual([1, 2, 3])
  })
  it('continues after the highest number the server already has', () => {
    const q = createEventQueue(3, async () => {}, { storage: memStorage(), startSeq: 41 })
    expect(q.add('page_hidden').seq).toBe(42)
  })
  it('drops a batch the server will never accept, keeps one it may accept later', async () => {
    const q1 = createEventQueue(1, vi.fn().mockRejectedValue({ status: 404 }), { storage: memStorage() })
    q1.add('page_hidden')
    await q1.flush()
    expect(q1.pending).toBe(0)
    const q2 = createEventQueue(2, vi.fn().mockRejectedValue({ status: 503 }), { storage: memStorage() })
    q2.add('page_hidden')
    await q2.flush()
    expect(q2.pending).toBe(1)
  })
})
