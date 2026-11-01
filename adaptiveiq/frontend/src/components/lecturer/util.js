/** Small helpers shared by the lecturer pages. */

export const REVIEW = {
  draft: { text: 'Needs review', tone: 'warning' },
  approved: { text: 'Approved', tone: 'success' },
  rejected: { text: 'Rejected', tone: 'error' },
  personal: { text: 'Student practice', tone: undefined },
}

export const QUIZ_STATUS = {
  generating: { text: 'Generating', tone: 'accent' },
  draft: { text: 'Draft', tone: 'warning' },
  published: { text: 'Published', tone: 'success' },
  archived: { text: 'Archived', tone: undefined },
}

export const SOURCE_TEXT = {
  manual: 'Written by hand',
  reference_text: 'From reference material',
  generated_notes: 'From AI-written study notes',
}

export const MATH_TEXT = {
  verified: 'Python check confirmed the answer',
  not_math: 'Not a calculation question',
  unchecked: 'Numeric answer could not be checked',
  wrong_key: 'Python check found a different answer',
  no_match: 'Python check matched no option',
}

export const FEEDBACK_TEXT = {
  immediate: 'Right after submitting',
  after_due: 'After the due date',
  manual: 'When I release it',
}

export const LATE_TEXT = { none: 'Not allowed', allow: 'Allowed, no penalty', penalty: 'Allowed with a penalty' }

/** Readable message from an ApiError (or anything thrown). */
export function errText(e) {
  if (!e) return ''
  return e.message || String(e)
}

export function slug(s) {
  return String(s || 'export').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'export'
}

const LS = 'aiq.lecturer.course'
export function rememberCourse(id) {
  try { localStorage.setItem(LS, String(id)) } catch { /* storage unavailable */ }
}
export function rememberedCourse() {
  try { return localStorage.getItem(LS) } catch { return null }
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    let ok = false
    try { ok = document.execCommand('copy') } catch { ok = false }
    ta.remove()
    return ok
  }
}

/** Splits a pasted list of emails on commas, semicolons, spaces and new lines. */
export function parseEmails(raw) {
  const parts = String(raw || '').split(/[\s,;]+/).map((s) => s.trim().toLowerCase()).filter(Boolean)
  return [...new Set(parts)]
}

export const looksLikeEmail = (s) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s)

export function wordCount(s) {
  return String(s || '').trim().split(/\s+/).filter(Boolean).length
}

/** 20 -> '20%', 12.345 -> '12.3%' */
export const pctg = (v) => (v == null ? '—' : `${Number(Number(v).toFixed(1))}%`)
