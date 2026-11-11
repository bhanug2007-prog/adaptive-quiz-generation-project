// Integrity monitoring during a monitored assessment attempt. Everything is detected in this browser; only
// small events (what, when, how long) are sent to the server. No video, image or audio leaves the computer.
import { useCallback, useEffect, useRef, useState } from 'react'
import { studentApi } from '../api/endpoints'
import { createFaceTracker, createVad, rmsDb } from './detectors'
import { createEventQueue } from './eventQueue'
import { createSpeechWarningGate, createWarningTracker } from './warnings'

const FLUSH_MS = 4000
const AUDIO_TICK_MS = 100
const MODEL_URL = '/mediapipe/blaze_face_short_range.tflite'
const WASM_URL = '/mediapipe/wasm'

function deviceError(e) {
  const n = e?.name || ''
  if (n === 'NotAllowedError' || n === 'SecurityError') return 'denied'
  return 'unavailable'                                   // NotFoundError, NotReadableError, no mediaDevices...
}

async function loadFaceDetector() {
  const { FaceDetector, FilesetResolver } = await import('@mediapipe/tasks-vision')
  const files = await FilesetResolver.forVisionTasks(WASM_URL)
  return FaceDetector.createFromOptions(files, {
    baseOptions: { modelAssetPath: MODEL_URL, delegate: 'CPU' }, runningMode: 'VIDEO', minDetectionConfidence: 0.6,
  })
}

export function useMonitoring({ attempt, sessionId, loadDetector = loadFaceDetector }) {
  const cfg = attempt?.monitoring || null
  const enabled = !!cfg
  const [started, setStarted] = useState(false)
  const [starting, setStarting] = useState(false)
  const [devices, setDevices] = useState({ camera: 'off', microphone: 'off' })   // off | on | denied | unavailable | lost
  const [isFullscreen, setIsFullscreen] = useState(() => typeof document !== 'undefined' && !!document.fullscreenElement)
  const [notice, setNotice] = useState(null)             // a short message after something was recorded
  const [faceHint, setFaceHint] = useState(null)         // face_none | face_multiple while it lasts
  const [record, setRecord] = useState(null)
  const [syncError, setSyncError] = useState(false)
  const q = useRef(null)
  const ready = useRef(null)
  const cleanup = useRef([])
  const hiddenAt = useRef(null)
  const cancelled = useRef(false)
  const fsSupported = typeof document !== 'undefined' && !!document.fullscreenEnabled

  // The queue continues the attempt's sequence numbers (after a reload too).
  useEffect(() => {
    if (!cfg || !sessionId) return undefined
    let live = true
    ready.current = studentApi.myMonitoring(sessionId)
      .then((r) => { if (live) setRecord(r); return Math.max(0, ...(r.events || []).map((e) => e.seq)) })
      .then((startSeq) => {
        if (!live) return null
        q.current = createEventQueue(sessionId, async (events) => {
          try {
            const next = await studentApi.monitoringEvents(sessionId, events)
            if (live) {
              if (next?.warning_count != null) setRecord((r) => ({ ...r, ...next }))
              setSyncError(false)
            }
          } catch (e) { if (live) setSyncError(true); throw e }
        }, { startSeq })
        q.current.flush()
        return q.current
      })
      .catch(() => {
        if (live) setNotice('Monitoring could not sync. Reconnect and reload this page before continuing.')
        return null
      })
    return () => { live = false }
  }, [enabled, sessionId])

  const add = useCallback((kind, opts) => q.current?.add(kind, opts), [])

  const stopAll = useCallback(() => {
    cancelled.current = true
    const fns = cleanup.current
    cleanup.current = []
    fns.reverse().forEach((f) => { try { f() } catch { /* ignore */ } })
  }, [])

  const start = useCallback(async () => {
    if (!cfg || started || starting) return
    setStarting(true)
    cancelled.current = false
    // Fullscreen must be asked first, while the click still counts as the student's action.
    let fsPromise = null
    if (cfg.fullscreen !== 'off' && fsSupported && !document.fullscreenElement) {
      try { fsPromise = document.documentElement.requestFullscreen()?.catch(() => null) } catch { fsPromise = null }
    }
    const queue = await ready.current
    if (!queue || cancelled.current) { setStarting(false); return }
    const status = { camera: 'not_requested', microphone: 'not_requested' }
    const warnings = createWarningTracker(sessionId, cfg.warning_policy, add)
    const shown = { camera: 'off', microphone: 'off' }
    let devicesSent = false

    if (cfg.camera) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240, facingMode: 'user' } })
        if (cancelled.current) { stream.getTracks().forEach((t) => t.stop()); return }
        cleanup.current.push(() => stream.getTracks().forEach((t) => t.stop()))
        status.camera = 'granted'
        shown.camera = 'on'
        const video = document.createElement('video')
        video.muted = true
        video.playsInline = true
        video.srcObject = stream
        await video.play().catch(() => null)
        if (cancelled.current) return
        const tracker = createFaceTracker({ confirm: 2 })
        let detector = null
        let timer = null
        let running = true
        const emit = (ep) => { if (ep) add(ep.kind, { at: new Date(ep.start), duration_ms: Math.round(ep.end - ep.start), details: { faces: ep.faces } }) }
        const tick = () => {
          if (!running) return
          if (detector && document.visibilityState === 'visible' && video.readyState >= 2) {
            try {
              const n = detector.detectForVideo(video, performance.now()).detections.length
              warnings.sample('face_none', n === 0)
              warnings.sample('face_multiple', n > 1, Date.now(), { faces: n })
              emit(tracker.push(n, Date.now()))
              setFaceHint(tracker.open)
            } catch {
              warnings.pause('face_none'); warnings.pause('face_multiple')
            }
          } else {
            warnings.pause('face_none'); warnings.pause('face_multiple')
          }
          timer = setTimeout(tick, cfg.face_interval_ms || 1500)
        }
        const track = stream.getVideoTracks()[0]
        if (track) {
          track.onended = () => {
            if (!running) return
            running = false
            clearTimeout(timer)
            warnings.pause('face_none'); warnings.pause('face_multiple')
            emit(tracker.flush(Date.now()))
            add('camera_lost', { details: { reason: 'camera stopped' } })
            setDevices((d) => ({ ...d, camera: 'lost' }))
            setFaceHint(null)
          }
        }
        cleanup.current.push(() => {
          running = false
          clearTimeout(timer)
          emit(tracker.flush(Date.now()))
          stream.getTracks().forEach((t) => { t.onended = null; t.stop() })
          detector?.close?.()
        })
        loadDetector().then((d) => { if (running) { detector = d; tick() } else d?.close?.() }).catch(() => {
          if (!running) return
          status.camera = 'unavailable'
          shown.camera = 'unavailable'
          add('camera_lost', { details: { reason: 'face detector could not load' } })
          setDevices((d) => ({ ...d, camera: 'unavailable' }))
          if (devicesSent) studentApi.monitoringDevices(sessionId, { ...status, camera: 'unavailable' }).catch(() => null)
        })
      } catch (e) {
        if (cancelled.current) return
        status.camera = deviceError(e)
        shown.camera = status.camera
        add('camera_denied', { details: { reason: status.camera } })
      }
    }

    if (cancelled.current) return
    if (cfg.microphone) {
      let stream, ctx
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        if (cancelled.current) { stream.getTracks().forEach((t) => t.stop()); return }
        cleanup.current.push(() => stream.getTracks().forEach((t) => t.stop()))
        status.microphone = 'granted'
        shown.microphone = 'on'
        const Ctx = window.AudioContext || window.webkitAudioContext
        ctx = new Ctx()
        cleanup.current.push(() => { ctx.close?.()?.catch(() => null) })
        await ctx.resume?.().catch(() => null)
        if (cancelled.current) return
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 2048
        ctx.createMediaStreamSource(stream).connect(analyser)
        const buf = new Float32Array(analyser.fftSize)
        const vad = createVad()
        const speechGate = createSpeechWarningGate()
        const emit = (seg) => { if (seg) add('speech', { at: new Date(seg.start), duration_ms: Math.round(seg.end - seg.start) }) }
        const id = setInterval(() => {
          analyser.getFloatTimeDomainData(buf)
          const now = Date.now()
          const level = rmsDb(buf)
          emit(vad.push(level, now))
          warnings.sample('speech', vad.active, now, {}, speechGate(level, vad.active, now))
        }, AUDIO_TICK_MS)
        let running = true
        const track = stream.getAudioTracks()[0]
        if (track) {
          track.onended = () => {
            if (!running) return
            running = false
            clearInterval(id)
            warnings.pause('speech')
            emit(vad.flush(Date.now()))
            add('microphone_lost', { details: { reason: 'microphone stopped' } })
            setDevices((d) => ({ ...d, microphone: 'lost' }))
          }
        }
        cleanup.current.push(() => {
          running = false
          clearInterval(id)
          emit(vad.flush(Date.now()))
          stream.getTracks().forEach((t) => { t.onended = null; t.stop() })
          ctx.close?.()
        })
      } catch (e) {
        stream?.getTracks().forEach((t) => t.stop())
        ctx?.close?.()?.catch(() => null)
        if (cancelled.current) return
        status.microphone = deviceError(e)
        shown.microphone = status.microphone
        add('microphone_denied', { details: { reason: status.microphone } })
      }
    }

    if (cancelled.current) return
    // Sample browser state while an incident is ongoing, including when focus is lost.
    let windowBlurred = false
    let fullscreenEntered = !!document.fullscreenElement
    const sampleBrowser = () => {
      if (cfg.tab) warnings.sample('page_hidden', document.visibilityState === 'hidden' || windowBlurred)
      if (cfg.fullscreen !== 'off' && fsSupported) {
        fullscreenEntered ||= !!document.fullscreenElement
        warnings.sample('fullscreen_exit', fullscreenEntered && !document.fullscreenElement)
      }
    }
    const warningBlur = () => { windowBlurred = true; sampleBrowser() }
    const warningFocus = () => { windowBlurred = false; sampleBrowser() }
    window.addEventListener('blur', warningBlur)
    window.addEventListener('focus', warningFocus)
    document.addEventListener('fullscreenchange', sampleBrowser)
    document.addEventListener('visibilitychange', sampleBrowser)
    const warningTimer = setInterval(sampleBrowser, 250)
    cleanup.current.push(() => {
      clearInterval(warningTimer)
      window.removeEventListener('blur', warningBlur)
      window.removeEventListener('focus', warningFocus)
      document.removeEventListener('fullscreenchange', sampleBrowser)
      document.removeEventListener('visibilitychange', sampleBrowser)
    })
    // Combine visibility and focus so the same departure is counted only once.
    if (cfg.tab) {
      let blurred = false
      const onVis = () => {
        const now = Date.now()
        if (document.visibilityState === 'hidden' || blurred) {
          if (hiddenAt.current == null) {
            hiddenAt.current = now
            const reason = document.visibilityState === 'hidden' ? 'tab_hidden' : 'window_blur'
            add('page_hidden', { at: new Date(now), details: { reason } })
          }
          q.current?.flush()
        } else if (hiddenAt.current != null) {
          const ms = now - hiddenAt.current
          hiddenAt.current = null
          add('page_visible', { at: new Date(now), duration_ms: ms })
          const s = Math.max(1, Math.round(ms / 1000))
          setNotice(`You left the quiz page for ${s} ${s === 1 ? 'second' : 'seconds'}. This was recorded for your lecturer.`)
        }
      }
      document.addEventListener('visibilitychange', onVis)
      const onBlur = () => { blurred = true; onVis() }
      const onFocus = () => { blurred = false; onVis() }
      window.addEventListener('blur', onBlur)
      window.addEventListener('focus', onFocus)
      cleanup.current.push(() => {
        document.removeEventListener('visibilitychange', onVis)
        window.removeEventListener('blur', onBlur)
        window.removeEventListener('focus', onFocus)
        if (hiddenAt.current != null) {
          add('page_visible', { duration_ms: Date.now() - hiddenAt.current, details: { reason: 'monitoring ended while away' } })
          hiddenAt.current = null
        }
      })
    }

    // Fullscreen.
    if (cfg.fullscreen !== 'off' && fsSupported) {
      let previousFullscreen = false
      const onFs = () => {
        const on = !!document.fullscreenElement
        setIsFullscreen(on)
        if (on === previousFullscreen) return
        previousFullscreen = on
        add(on ? 'fullscreen_enter' : 'fullscreen_exit')
        if (!on) setNotice('You left full screen. This was recorded for your lecturer.')
      }
      document.addEventListener('fullscreenchange', onFs)
      cleanup.current.push(() => document.removeEventListener('fullscreenchange', onFs))
      await fsPromise
      if (cancelled.current) return
      onFs()
    }

    add('monitoring_started', { details: { camera: status.camera, microphone: status.microphone } })
    devicesSent = true
    studentApi.monitoringDevices(sessionId, status).catch(() => null)
    const flushId = setInterval(() => q.current?.flush(), FLUSH_MS)
    const onOnline = () => q.current?.flush()
    window.addEventListener('online', onOnline)
    cleanup.current.push(() => { clearInterval(flushId); window.removeEventListener('online', onOnline) })
    setDevices(shown)
    setStarted(true)
    setStarting(false)
    queue.flush()
  }, [cfg, started, starting, fsSupported, sessionId, add])

  const enterFullscreen = useCallback(() => {
    try { document.documentElement.requestFullscreen()?.catch(() => null) } catch { /* not allowed */ }
  }, [])

  /** Stops every detector, sends what is left (waits at most `waitMs`) and leaves full screen. */
  const finish = useCallback(async (waitMs = 3000) => {
    stopAll()
    q.current?.stop()
    if (q.current) await Promise.race([q.current.flush(), new Promise((r) => setTimeout(r, waitMs))])
    if (typeof document !== 'undefined' && document.fullscreenElement) document.exitFullscreen?.().catch(() => null)
  }, [stopAll])

  useEffect(() => () => { stopAll(); q.current?.flush() }, [stopAll])

  return {
    record, syncError, reportProblem: (body) => studentApi.monitoringReport(sessionId, body),
    enabled: !!cfg, cfg, started, starting, start, finish, devices, faceHint,
    notice, clearNotice: () => setNotice(null),
    fullscreenSupported: fsSupported, isFullscreen, enterFullscreen,
    needsFullscreen: !!cfg && started && cfg.fullscreen === 'required' && fsSupported && !isFullscreen,
  }
}
