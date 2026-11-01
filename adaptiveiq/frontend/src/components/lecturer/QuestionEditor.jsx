import { useId, useState } from 'react'
import { Alert, Button, Field, Input, Select, Textarea } from '../ui'
import { errText } from './util'

const LETTERS = ['A', 'B', 'C', 'D']

export function questionProblems(v) {
  const p = {}
  if (!v.text || v.text.trim().length < 10) p.text = 'Write at least 10 characters.'
  else if (v.text.length > 2000) p.text = 'Keep it under 2000 characters.'
  const opts = v.options.map((o) => o.trim())
  if (opts.some((o) => !o)) p.options = 'All four options need text.'
  else if (new Set(opts.map((o) => o.toLowerCase())).size < 4) p.options = 'The four options must be different.'
  else if (opts.some((o) => o.length > 500)) p.options = 'Each option must be at most 500 characters.'
  if (!LETTERS.includes(v.correct_label)) p.correct = 'Choose the correct option.'
  if ((v.explanation || '').length > 3000) p.explanation = 'Keep the explanation under 3000 characters.'
  if (v.needTopic && !v.topic_id) p.topic = 'Choose a topic.'
  return p
}

export function fromQuestion(q) {
  return {
    text: q?.text || '',
    options: q ? LETTERS.map((l) => q.options.find((o) => o.label === l)?.text || '') : ['', '', '', ''],
    correct_label: q?.options.find((o) => o.is_correct)?.label || '',
    explanation: q?.explanation || '',
    difficulty: q?.difficulty || 'medium',
    objective_id: q?.objective_id ? String(q.objective_id) : '',
    topic_id: q?.topic_id ? String(q.topic_id) : '',
  }
}

/**
 * Form for writing or editing a multiple-choice question.
 * topics: optional [{topic_id, label, objectives}] to pick a topic (create mode).
 * objectives: [{id, text}] for the question's topic (edit mode).
 */
export default function QuestionEditor({ initial, topics, objectives, onSubmit, onCancel, submitLabel = 'Save', busy, note }) {
  const [v, setV] = useState(() => fromQuestion(initial))
  const [touched, setTouched] = useState(false)
  const [error, setError] = useState(null)
  const base = useId()
  const set = (k, val) => setV((s) => ({ ...s, [k]: val }))
  const problems = questionProblems({ ...v, needTopic: !!topics })
  const show = touched ? problems : {}
  const objs = topics ? (topics.find((t) => String(t.topic_id) === v.topic_id)?.objectives || []) : (objectives || [])

  const submit = async (e) => {
    e.preventDefault()
    setTouched(true)
    setError(null)
    if (Object.keys(problems).length) return
    const body = {
      text: v.text.trim(), options: v.options.map((o) => o.trim()), correct_label: v.correct_label,
      explanation: v.explanation.trim() || null, difficulty: v.difficulty,
      objective_id: v.objective_id ? Number(v.objective_id) : null,
    }
    if (topics) body.topic_id = Number(v.topic_id)
    try {
      await onSubmit(body)
    } catch (err) {
      setError(errText(err))
    }
  }

  return (
    <form className="stack lc-qedit" onSubmit={submit} noValidate>
      {note}
      {topics && (
        <Field label="Topic" error={show.topic}>
          {(a) => (
            <Select {...a} value={v.topic_id} onChange={(e) => setV((s) => ({ ...s, topic_id: e.target.value, objective_id: '' }))}>
              <option value="">Choose a topic</option>
              {topics.map((t) => <option key={t.topic_id} value={t.topic_id}>{t.label}</option>)}
            </Select>
          )}
        </Field>
      )}
      <Field label="Question" error={show.text}>
        {(a) => <Textarea {...a} rows={3} value={v.text} onChange={(e) => set('text', e.target.value)} maxLength={2000} />}
      </Field>
      <fieldset className="lc-fieldset">
        <legend className="field__label">Options (select the correct one)</legend>
        <div className="lc-opt-grid">
          {LETTERS.map((l, i) => (
            <div key={l} className="lc-opt-edit" data-correct={v.correct_label === l || undefined}>
              <label className="lc-opt-edit__radio">
                <input type="radio" name={`${base}-correct`} value={l} checked={v.correct_label === l}
                  onChange={() => set('correct_label', l)} aria-label={`Option ${l} is correct`} />
                <span aria-hidden="true">{l}</span>
              </label>
              <Input aria-label={`Option ${l}`} value={v.options[i]} maxLength={500}
                onChange={(e) => set('options', v.options.map((o, k) => (k === i ? e.target.value : o)))} />
            </div>
          ))}
        </div>
        {(show.options || show.correct) && <p className="field__error" role="alert">{show.options || show.correct}</p>}
      </fieldset>
      <Field label="Explanation" hint="Shown to students with their feedback." error={show.explanation}>
        {(a) => <Textarea {...a} rows={3} value={v.explanation} onChange={(e) => set('explanation', e.target.value)} maxLength={3000} />}
      </Field>
      <div className="grid-2">
        <Field label="Difficulty">
          {(a) => (
            <Select {...a} value={v.difficulty} onChange={(e) => set('difficulty', e.target.value)}>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </Select>
          )}
        </Field>
        <Field label="Learning objective" hint={objs.length ? undefined : 'This topic has no learning objectives yet.'}>
          {(a) => (
            <Select {...a} value={v.objective_id} onChange={(e) => set('objective_id', e.target.value)} disabled={!objs.length}>
              <option value="">None</option>
              {objs.map((o) => <option key={o.id} value={o.id}>{o.text}</option>)}
            </Select>
          )}
        </Field>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        {onCancel && <Button variant="ghost" onClick={onCancel}>Cancel</Button>}
        <Button type="submit" variant="primary" loading={busy}>{submitLabel}</Button>
      </div>
    </form>
  )
}
