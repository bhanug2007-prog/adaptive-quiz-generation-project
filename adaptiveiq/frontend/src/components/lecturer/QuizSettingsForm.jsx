import { useMemo, useState } from 'react'
import { Save } from 'lucide-react'
import { Alert, Button, Card, Checkbox, Field, Input, Select, Textarea } from '../ui'
import { fromLocalInput, toLocalInput } from '../../utils/format'
import { errText, pctg } from './util'

function init(q) {
  return {
    title: q.title || '', instructions: q.instructions || '', graded: q.graded,
    attempts_allowed: String(q.attempts_allowed || 1), time_limit_min: q.time_limit_min ? String(q.time_limit_min) : '',
    opens_at: toLocalInput(q.opens_at), due_at: toLocalInput(q.due_at), closes_at: toLocalInput(q.closes_at),
    late_policy: q.late_policy || 'none', late_penalty_pct: String(q.late_penalty_pct ?? 0),
    shuffle_questions: q.shuffle_questions, shuffle_options: q.shuffle_options,
    feedback_release: q.feedback_release || 'immediate', contribution_pct: String(q.contribution_pct ?? 0),
    confidence_enabled: q.confidence_enabled, target_duration_min: q.target_duration_min ? String(q.target_duration_min) : '',
  }
}

/** Client-side checks that mirror the API's publish validation, shown as hints before saving. */
export function settingsProblems(v, cap) {
  const p = {}
  if (v.title.trim().length < 2) p.title = 'Give the quiz a title.'
  const att = Number(v.attempts_allowed)
  if (!(Number.isInteger(att) && att >= 1 && att <= 20)) p.attempts_allowed = 'Allow 1 to 20 attempts.'
  if (v.time_limit_min && !(Number(v.time_limit_min) >= 1 && Number(v.time_limit_min) <= 300)) p.time_limit_min = 'Use 1 to 300 minutes, or leave empty for no limit.'
  if (v.opens_at && v.due_at && new Date(v.opens_at) >= new Date(v.due_at)) p.due_at = 'The due date must be after the opening date.'
  if (v.late_policy !== 'none') {
    if (!v.due_at) p.due_at = 'Late submissions need a due date.'
    else if (!v.closes_at || new Date(v.closes_at) <= new Date(v.due_at)) p.closes_at = 'Late submissions need a final close date after the due date.'
  }
  if (v.late_policy === 'penalty' && !(Number(v.late_penalty_pct) >= 0 && Number(v.late_penalty_pct) <= 100)) p.late_penalty_pct = 'Use 0 to 100.'
  if (v.feedback_release === 'after_due' && !v.due_at) p.feedback_release = 'Releasing feedback after the due date needs a due date.'
  const c = Number(v.contribution_pct)
  if (!(c >= 0 && c <= 100)) p.contribution_pct = 'Use 0 to 100.'
  else if (v.graded && cap && cap.available != null && c > cap.available + 1e-9) {
    p.contribution_warn = `Over the subject's cap: other quizzes already use ${pctg(cap.used)} of ${pctg(cap.cap)}, so this one can be at most ${pctg(cap.available)}. Publishing will be refused.`
  }
  if (v.target_duration_min && !(Number(v.target_duration_min) >= 1 && Number(v.target_duration_min) <= 300)) p.target_duration_min = 'Use 1 to 300 minutes.'
  return p
}

export function toBody(v) {
  return {
    title: v.title.trim(), instructions: v.instructions.trim() || null, graded: v.graded,
    attempts_allowed: Number(v.attempts_allowed), time_limit_min: v.time_limit_min ? Number(v.time_limit_min) : null,
    opens_at: fromLocalInput(v.opens_at), due_at: fromLocalInput(v.due_at),
    closes_at: v.late_policy === 'none' ? null : fromLocalInput(v.closes_at),
    late_policy: v.late_policy, late_penalty_pct: v.late_policy === 'penalty' ? Number(v.late_penalty_pct) : 0,
    shuffle_questions: v.shuffle_questions, shuffle_options: v.shuffle_options, feedback_release: v.feedback_release,
    contribution_pct: v.graded ? Number(v.contribution_pct) : 0, confidence_enabled: v.confidence_enabled,
    target_duration_min: v.target_duration_min ? Number(v.target_duration_min) : null,
  }
}

export default function QuizSettingsForm({ quiz, onSave }) {
  const [v, setV] = useState(() => init(quiz))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [touched, setTouched] = useState(false)
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  const cap = quiz.weight_cap_pct != null
    ? { cap: quiz.weight_cap_pct, used: quiz.weight_used_elsewhere_pct || 0, available: Math.max(0, quiz.weight_cap_pct - (quiz.weight_used_elsewhere_pct || 0)) }
    : null
  const problems = settingsProblems(v, cap)
  const blocking = Object.keys(problems).filter((k) => k !== 'contribution_warn')
  const show = touched ? problems : { contribution_warn: problems.contribution_warn }
  const published = quiz.status === 'published'
  const lockedField = () => false
  const contribution = Number(v.contribution_pct) || 0
  const tz = useMemo(() => Intl.DateTimeFormat().resolvedOptions().timeZone, [])

  const submit = async (e) => {
    e.preventDefault()
    setTouched(true)
    setError(null)
    if (blocking.length) return
    // Send only what changed: a published quiz with attempts refuses changes to most fields.
    const body = toBody(v)
    const before = toBody(init(quiz))
    Object.keys(body).forEach((k) => { if (JSON.stringify(body[k]) === JSON.stringify(before[k])) delete body[k] })
    if (!Object.keys(body).length) { setError(null); await onSave(null); return }
    setBusy(true)
    try {
      await onSave(body)
    } catch (err) {
      setError(errText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="stack-lg" onSubmit={submit} noValidate>
      {published && <Alert tone="info">This quiz is published. Once students start it, only the title, instructions, dates, late policy and feedback release can change.</Alert>}
      <Card title="Basics">
        <div className="lc-form-grid">
          <Field label="Title" error={show.title} className="span-all">{(a) => <Input {...a} value={v.title} onChange={set('title')} maxLength={200} />}</Field>
          <Field label="Instructions for students (optional)" className="span-all">{(a) => <Textarea {...a} rows={3} maxLength={4000} value={v.instructions} onChange={set('instructions')} />}</Field>
          <Field label="Type">
            {(a) => (
              <Select {...a} value={v.graded ? 'graded' : 'practice'} onChange={(e) => setV((s) => ({ ...s, graded: e.target.value === 'graded' }))} disabled={lockedField('graded')}>
                <option value="graded">Graded assessment</option>
                <option value="practice">Practice only (not graded)</option>
              </Select>
            )}
          </Field>
          <Field label="Attempts allowed" error={show.attempts_allowed}>{(a) => <Input {...a} type="number" min={1} max={20} value={v.attempts_allowed} onChange={set('attempts_allowed')} disabled={lockedField('attempts_allowed')} />}</Field>
          <Field label="Time limit in minutes" hint="Leave empty for no limit." error={show.time_limit_min}>{(a) => <Input {...a} type="number" min={1} max={300} value={v.time_limit_min} onChange={set('time_limit_min')} disabled={lockedField('time_limit_min')} />}</Field>
          <Field label="Target duration in minutes (optional)" error={show.target_duration_min}>{(a) => <Input {...a} type="number" min={1} max={300} value={v.target_duration_min} onChange={set('target_duration_min')} disabled={lockedField('target_duration_min')} />}</Field>
        </div>
      </Card>

      <Card title="Availability" subtitle={`Times are in your time zone (${tz}).`}>
        <div className="lc-form-grid">
          <Field label="Opens (optional)" hint="Empty means it opens when published.">{(a) => <Input {...a} type="datetime-local" value={v.opens_at} onChange={set('opens_at')} disabled={lockedField('opens_at')} />}</Field>
          <Field label="Due (optional)" error={show.due_at}>{(a) => <Input {...a} type="datetime-local" value={v.due_at} onChange={set('due_at')} />}</Field>
          <Field label="Late submissions" error={show.late_policy}>
            {(a) => (
              <Select {...a} value={v.late_policy} onChange={set('late_policy')}>
                <option value="none">Not allowed</option>
                <option value="allow">Allowed, no penalty</option>
                <option value="penalty">Allowed with a penalty</option>
              </Select>
            )}
          </Field>
          {v.late_policy !== 'none' && (
            <Field label="Final close (no submissions after this)" error={show.closes_at}>{(a) => <Input {...a} type="datetime-local" value={v.closes_at} onChange={set('closes_at')} />}</Field>
          )}
          {v.late_policy === 'penalty' && (
            <Field label="Late penalty (% taken off the score)" error={show.late_penalty_pct}>{(a) => <Input {...a} type="number" min={0} max={100} value={v.late_penalty_pct} onChange={set('late_penalty_pct')} />}</Field>
          )}
        </div>
      </Card>

      <Card title="Delivery and feedback">
        <div className="lc-form-grid">
          <Field label="When students see answers and explanations" error={show.feedback_release}>
            {(a) => (
              <Select {...a} value={v.feedback_release} onChange={set('feedback_release')}>
                <option value="immediate">Right after they submit</option>
                <option value="after_due">After the due date</option>
                <option value="manual">When I release it</option>
              </Select>
            )}
          </Field>
          <div className="stack" style={{ gap: 'var(--space-2)', alignContent: 'start' }}>
            <Checkbox label="Shuffle question order for each student" checked={v.shuffle_questions} onChange={set('shuffle_questions')} disabled={lockedField('shuffle_questions')} />
            <Checkbox label="Shuffle option order" checked={v.shuffle_options} onChange={set('shuffle_options')} disabled={lockedField('shuffle_options')} />
            <Checkbox label="Ask students how confident they are in each answer" checked={v.confidence_enabled} onChange={set('confidence_enabled')} disabled={lockedField('confidence_enabled')} />
          </div>
        </div>
      </Card>

      {v.graded && (
        <Card title="Assessment weighting" subtitle={quiz.subject_name ? `Contribution to ${quiz.subject_name}'s internal assessment.` : undefined}>
          <div className="lc-form-grid">
            <Field label="Contribution (% of the subject grade)" error={show.contribution_pct}
              hint={cap ? `Subject cap ${pctg(cap.cap)}. Other quizzes use ${pctg(cap.used)}, so up to ${pctg(cap.available)} is available.` : undefined}>
              {(a) => <Input {...a} type="number" min={0} max={100} step="0.5" value={v.contribution_pct} onChange={set('contribution_pct')} disabled={lockedField('contribution_pct')} />}
            </Field>
            <div className="lc-three">
              <p className="lc-mini-label">Three values kept separate</p>
              <dl className="lc-dl">
                <div><dt>Raw score</dt><dd>out of {quiz.max_marks} marks</dd></div>
                <div><dt>Quiz percentage</dt><dd>raw score ÷ {quiz.max_marks} × 100</dd></div>
                <div><dt>Contribution</dt><dd>percentage × {contribution}% of the subject grade (a full score earns {contribution} points)</dd></div>
              </dl>
            </div>
          </div>
          {show.contribution_warn && <Alert tone="warning">{show.contribution_warn}</Alert>}
        </Card>
      )}

      {error && <Alert tone="error" title="Settings not saved">{error}</Alert>}
      {touched && blocking.length > 0 && <Alert tone="error">Fix the highlighted fields first.</Alert>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <Button type="submit" variant="primary" icon={Save} loading={busy}>Save settings</Button>
      </div>
    </form>
  )
}
