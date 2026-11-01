/** Mastery labels: same keys as the backend (app/ml/mastery.py). */
export const LABELS = {
  not_attempted: { text: 'Not attempted', color: 'var(--m-none)' },
  insufficient_evidence: { text: 'Insufficient evidence', color: 'var(--m-insufficient)' },
  needs_improvement: { text: 'Needs improvement', color: 'var(--m-needs)' },
  developing: { text: 'Developing', color: 'var(--m-developing)' },
  proficient: { text: 'Proficient', color: 'var(--m-proficient)' },
  strong: { text: 'Strong evidence of mastery', color: 'var(--m-strong)' },
}

export const STATUS_TEXT = {
  weak: 'Weak area', developing: 'Developing', ok: 'On track', insufficient_evidence: 'Insufficient evidence',
  not_attempted: 'Not attempted', upcoming_assessment: 'Upcoming assessment',
}

export const DIFFICULTY_TEXT = { easy: 'Easy', medium: 'Medium', hard: 'Hard', mixed: 'Mixed', adaptive: 'Adaptive' }

export function pct(v, digits = 0) {
  if (v == null || Number.isNaN(v)) return '—'
  return `${Number(v).toFixed(digits)}%`
}

/** v in 0..1 */
export function pct01(v, digits = 0) {
  return v == null ? '—' : pct(v * 100, digits)
}

const dtf = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const dttf = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

export function date(v) {
  return v ? dtf.format(new Date(v)) : '—'
}

export function dateTime(v) {
  return v ? dttf.format(new Date(v)) : '—'
}

export function relative(v) {
  if (!v) return '—'
  const s = (new Date(v).getTime() - Date.now()) / 1000
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  const abs = Math.abs(s)
  if (abs < 60) return rtf.format(Math.round(s), 'second')
  if (abs < 3600) return rtf.format(Math.round(s / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(s / 3600), 'hour')
  return rtf.format(Math.round(s / 86400), 'day')
}

export function duration(sec) {
  if (sec == null) return '—'
  const s = Math.round(sec)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  if (h) return `${h} h ${m} min`
  if (m) return `${m} min ${r ? `${r} s` : ''}`.trim()
  return `${r} s`
}

/** For <input type="datetime-local"> */
export function toLocalInput(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const off = d.getTimezoneOffset()
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 16)
}

export function fromLocalInput(v) {
  return v ? new Date(v).toISOString() : null
}

export function plural(n, word, many = `${word}s`) {
  return `${n} ${n === 1 ? word : many}`
}
