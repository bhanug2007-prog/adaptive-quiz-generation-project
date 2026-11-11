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
  document: 'From uploaded document',
}

export function formatSourceRef(ref) {
  if (!ref || typeof ref !== 'object') return ''
  const parts = []
  if (ref.document_name) parts.push(ref.document_name)
  if (ref.page != null) {
    parts.push(ref.page_end && ref.page_end !== ref.page ? `pp. ${ref.page}–${ref.page_end}` : `p. ${ref.page}`)
  }
  const sec = ref.section || ref.heading
  if (sec) parts.push(sec)
  return parts.join(' · ')
}

export const MATH_TEXT = {
  verified: 'Python check confirmed the answer',
  not_math: 'Not a calculation question',
  unchecked: 'Numeric answer could not be checked',
  wrong_key: 'Python check found a different answer',
  no_match: 'Python check matched no option',
  ambiguous: 'Multiple options match the computed answer',
  unsupported: 'Calculation used an unsupported expression',
}

/** AI review state of a question (validation.quality.status). */
export const QUALITY = {
  passed: { text: 'AI review passed', tone: 'success' },
  failed: { text: 'AI review failed', tone: 'error' },
  not_checked: { text: 'AI review not done', tone: undefined },
}

export const AI_CHECKS = [
  ['correctness', 'Answer key', (a) => ({ correct: 'Looks correct', incorrect: 'Looks wrong', unsure: 'Reviewer unsure' }[a.verdict] || a.verdict)],
  ['relevance', 'Topic', (a) => (a.ok ? 'Tests the topic' : 'Off topic')],
  ['difficulty', 'Judged difficulty', (a) => a.assessed],
  ['options', 'Wrong options', (a) => (a.ok ? 'Distinct and plausible' : 'Weak or overlapping')],
  ['multiple_correct', 'More than one correct', (a) => (a.value ? 'Possibly' : 'No')],
  ['ambiguity', 'Ambiguous', (a) => (a.ambiguous ? 'Yes' : 'No')],
  ['explanation', 'Explanation', (a) => (a.supports_answer ? 'Supports the answer' : 'Does not support the answer')],
  ['clarity', 'Wording', (a) => (a.ok ? 'Clear' : 'Unclear')],
]

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
