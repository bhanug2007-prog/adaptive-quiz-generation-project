// Plain, neutral words for monitoring events and statuses (shared by the student and lecturer pages).
export const EVENT_TEXT = {
  monitoring_started: 'Monitoring turned on',
  page_hidden: 'Left the quiz page',
  page_visible: 'Came back to the quiz page',
  fullscreen_enter: 'Entered full screen',
  fullscreen_exit: 'Fullscreen exited',
  face_none: 'No face visible',
  face_multiple: 'More than one face visible',
  camera_denied: 'Camera not allowed or not found',
  camera_lost: 'Camera stopped',
  speech: 'Speech-like sound',
  microphone_denied: 'Microphone not allowed or not found',
  microphone_lost: 'Microphone stopped',
}

export const STATUS_TEXT = {
  normal: 'Normal',
  event_recorded: 'Event recorded',
  needs_review: 'Needs review',
  unavailable: 'Monitoring unavailable',
  not_monitored: 'Not monitored',
}
export const STATUS_TONE = {
  normal: 'success',
  event_recorded: 'accent',
  needs_review: 'warning',
  unavailable: 'warning',
  not_monitored: undefined,
}
export const REVIEW_TEXT = {
  none: 'Not reviewed',
  no_concern: 'Reviewed: no concern',
  follow_up: 'Reviewed — follow-up needed',
}
export const DEVICE_STATE = {
  granted: 'allowed',
  denied: 'not allowed',
  unavailable: 'not found',
  lost: 'stopped',
  not_requested: 'not requested',
}
export const SIGNAL_STATE = {
  active: 'Active',
  unavailable: 'Unavailable',
  not_monitored: 'Not monitored',
}

export function secs(ms) {
  if (ms == null) return ''
  const s = Math.round(ms / 1000)
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`
}

export function eventSource(e) {
  if (e.source) return e.source
  if (e.kind === 'page_hidden' || e.kind === 'page_visible') {
    return e.details?.reason === 'window_blur' ? 'Window focus monitor' : 'Tab visibility monitor'
  }
  if (e.kind === 'fullscreen_enter' || e.kind === 'fullscreen_exit') return 'Fullscreen monitor'
  if (['face_none', 'face_multiple', 'camera_denied', 'camera_lost'].includes(e.kind)) return 'Camera face detector'
  if (['speech', 'microphone_denied', 'microphone_lost'].includes(e.kind)) return 'Microphone audio monitor'
  if (e.kind === 'monitoring_started') return 'Monitoring setup'
  return 'Browser monitor'
}

export function eventDeviceText(e) {
  const ds = e.device_state
  const parts = []
  if (ds?.camera) parts.push(`Camera ${DEVICE_STATE[ds.camera] || ds.camera}`)
  else if (e.kind === 'camera_denied' && e.details?.reason) parts.push(`Camera ${DEVICE_STATE[e.details.reason] || e.details.reason}`)
  if (ds?.microphone) parts.push(`Microphone ${DEVICE_STATE[ds.microphone] || ds.microphone}`)
  else if (e.kind === 'microphone_denied' && e.details?.reason) parts.push(`Microphone ${DEVICE_STATE[e.details.reason] || e.details.reason}`)
  if (!parts.length && e.kind === 'monitoring_started' && e.details) {
    if (e.details.camera && e.details.camera !== 'not_requested') parts.push(`Camera ${DEVICE_STATE[e.details.camera] || e.details.camera}`)
    if (e.details.microphone && e.details.microphone !== 'not_requested') parts.push(`Microphone ${DEVICE_STATE[e.details.microphone] || e.details.microphone}`)
  }
  return parts.length ? parts.join(' · ') : null
}

export function eventDetailHint(e) {
  if (e.kind === 'face_none') return 'Face not detected'
  if (e.kind === 'face_multiple') return 'Multiple faces detected'
  if (e.kind === 'speech') return 'Speech-like audio activity detected'
  return null
}

export function eventLine(e) {
  if (e.kind === 'activity_warning') return `${e.details?.confirmed ? 'Activity warning' : 'Activity signal (not counted)'}: ${EVENT_TEXT[e.details?.signal] || 'Monitoring activity'}`
  if (e.kind === 'student_report') return `Student-reported ${e.details?.category === 'false_alert' ? 'false alert' : 'device problem'}${e.details?.event_seq != null ? ` (event ${e.details.event_seq})` : ''}${e.details?.note ? `: ${e.details.note}` : ''}`
  if (e.kind === 'page_hidden') {
    if (e.details?.reason === 'window_blur') return 'Quiz window lost focus'
    if (e.details?.reason === 'tab_hidden') return 'Switched away from quiz tab'
  }
  const base = EVENT_TEXT[e.kind] || e.kind
  const extra = []
  if (e.kind === 'page_visible' && e.duration_ms != null) extra.push(`away ${secs(e.duration_ms)}`)
  else if (e.duration_ms != null) extra.push(`for ${secs(e.duration_ms)}`)
  if (e.kind === 'face_multiple' && e.details?.faces) extra.push(`up to ${e.details.faces} faces`)
  if (e.kind === 'monitoring_started' && e.details) {
    const d = [e.details.camera && e.details.camera !== 'not_requested' ? `camera ${DEVICE_STATE[e.details.camera] || e.details.camera}` : null,
      e.details.microphone && e.details.microphone !== 'not_requested' ? `microphone ${DEVICE_STATE[e.details.microphone] || e.details.microphone}` : null].filter(Boolean)
    if (d.length) extra.push(d.join(', '))
  }
  if (e.details?.reason && !['denied', 'unavailable', 'tab_hidden', 'window_blur', 'camera stopped', 'microphone stopped'].includes(e.details.reason)) extra.push(e.details.reason)
  return extra.length ? `${base} (${extra.join(', ')})` : base
}
