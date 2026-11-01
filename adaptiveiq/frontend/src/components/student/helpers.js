/** Small helpers shared by the student pages. */

export const STATE_META = {
  upcoming: { text: 'Upcoming', tone: undefined },
  open: { text: 'Open', tone: 'teal' },
  in_progress: { text: 'In progress', tone: 'accent' },
  late_open: { text: 'Late submission open', tone: 'warning' },
  submitted: { text: 'Submitted', tone: 'success' },
  expired: { text: 'Closed', tone: 'error' },
}

export const TREND_TONE = { improving: 'success', declining: 'error', stable: undefined, not_enough_data: undefined }

/** Link to the Practice Lab with the form prefilled (subject, topic, topic_id, difficulty). */
export function practiceHref(p = {}) {
  const s = new URLSearchParams()
  if (p.subject) s.set('subject', p.subject)
  if (p.topic) s.set('topic', p.topic)
  if (p.topic_id) s.set('topic_id', String(p.topic_id))
  if (p.difficulty) s.set('difficulty', p.difficulty)
  const q = s.toString()
  return `/student/practice${q ? `?${q}` : ''}`
}

/** sessionStorage that never throws (private mode, blocked storage). */
export const safeSession = {
  get(k) { try { return window.sessionStorage.getItem(k) } catch { return null } },
  set(k, v) { try { window.sessionStorage.setItem(k, v) } catch { /* ignore */ } },
  del(k) { try { window.sessionStorage.removeItem(k) } catch { /* ignore */ } },
}

/** "8 questions answered, 6 correct" plus wrong / skipped kept apart. */
export function evidenceSentence(t) {
  if (!t || !t.answers) return 'No answers on this topic yet.'
  const q = `${t.unique_questions} ${t.unique_questions === 1 ? 'question' : 'questions'}`
  const counts = [`${t.correct} correct`, `${t.incorrect} wrong`]
  if (t.skipped) counts.push(`${t.skipped} skipped`)
  return t.answers > t.unique_questions
    ? `${t.answers} answers on ${q}: ${counts.join(', ')}`
    : `${q} answered: ${counts.join(', ')}`
}

export const isInsufficient = (t) => !t || !t.answers || t.label === 'insufficient_evidence' || t.label === 'not_attempted'

/** Questions / answers due-state helpers for the quiz card. */
export function quizAction(card) {
  if (!card) return null
  if (card.state === 'in_progress') return { label: 'Resume', primary: true }
  if (card.state === 'open' || card.state === 'late_open') {
    if (card.kind === 'practice' || !card.attempts_allowed || card.attempts_used < card.attempts_allowed) {
      return { label: card.attempts_used ? 'Start another attempt' : 'Start quiz', primary: true }
    }
  }
  if (card.state === 'submitted' && card.kind === 'practice') return { label: 'Practise again', primary: false }
  return null
}

export function attemptsLeft(card) {
  if (!card || card.kind === 'practice' || !card.attempts_allowed) return null
  return Math.max(0, card.attempts_allowed - card.attempts_used)
}
