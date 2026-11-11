import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { FlaskConical, Info, Play, RotateCcw, Sparkles, X } from 'lucide-react'
import {
  Alert, Button, Card, Checkbox, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, Segmented, Select, Textarea, useToast,
} from '../../components/ui'
import DocumentSourcePicker from '../../components/quiz/DocumentSourcePicker'
import GenerationProgress from '../../components/quiz/GenerationProgress'
import { useApi } from '../../api/useApi'
import { studentApi, topicsApi } from '../../api/endpoints'
import { useGenerationRun } from '../../hooks/useGenerationRun'
import { useModelHealth } from '../../hooks/useModelHealth'
import { DIFFICULTY_TEXT } from '../../utils/format'
import QuizListItem from '../../components/student/QuizListItem'
import { safeSession } from '../../components/student/helpers'

export const RUN_KEY = 'aiq.student.practiceRun'
const COUNTS = [5, 10, 15, 20]
const DIFFS = ['adaptive', 'mixed', 'easy', 'medium', 'hard']
const DIFF_HINT = {
  adaptive: 'Picks the level from your mastery on this topic.',
  mixed: 'A spread of easy, medium and hard questions.',
  easy: 'Recall and basic understanding.',
  medium: 'Applying the idea to a short case.',
  hard: 'Multi-step reasoning and edge cases.',
}
const words = (s) => (s.trim() ? s.trim().split(/\s+/).length : 0)

function readRun() {
  try { return JSON.parse(safeSession.get(RUN_KEY) || 'null') } catch { return null }
}

/** Debounced recommended-difficulty lookup for the "adaptive" option. */
function useRecommended(enabled, subject, topic, topicId) {
  const [state, setState] = useState({ data: null, error: null, loading: false })
  useEffect(() => {
    if (!enabled || (!topicId && (subject.trim().length < 2 || topic.trim().length < 2))) {
      setState({ data: null, error: null, loading: false })
      return undefined
    }
    let alive = true
    setState((s) => ({ ...s, loading: true }))
    const t = setTimeout(async () => {
      try {
        const d = await studentApi.recommendedDifficulty({ subject: subject.trim() || 'x', topic: topic.trim() || 'x', topic_id: topicId || undefined })
        if (alive) setState({ data: d, error: null, loading: false })
      } catch (e) {
        if (alive) setState({ data: null, error: e, loading: false })
      }
    }, 400)
    return () => { alive = false; clearTimeout(t) }
  }, [enabled, subject, topic, topicId])
  return state
}

function PracticeForm({ choices, onStarted, disabledReason }) {
  const [params] = useSearchParams()
  const preTopicId = params.get('topic_id')
  const hasChoices = choices.length > 0
  const preMatch = preTopicId && choices.find((c) => String(c.topic_id) === preTopicId)
  const [mode, setMode] = useState('topic')
  const [source, setSource] = useState(preMatch ? 'course' : params.get('topic') ? 'free' : hasChoices ? 'course' : 'free')
  const [topicId, setTopicId] = useState(preMatch ? String(preMatch.topic_id) : hasChoices ? String(choices[0].topic_id) : '')
  const [subject, setSubject] = useState(params.get('subject') || '')
  const [topic, setTopic] = useState(params.get('topic') || '')
  const [unit, setUnit] = useState('')
  const [count, setCount] = useState('5')
  const [difficulty, setDifficulty] = useState(DIFFS.includes(params.get('difficulty')) ? params.get('difficulty') : 'adaptive')
  const [timeLimit, setTimeLimit] = useState('')
  const [confidence, setConfidence] = useState(true)
  const [reference, setReference] = useState('')
  const [doc, setDoc] = useState(null)
  const [docSection, setDocSection] = useState('')
  const [docFocus, setDocFocus] = useState('')
  const [docBusy, setDocBusy] = useState(false)
  const [errors, setErrors] = useState({})
  const [apiError, setApiError] = useState(null)
  const [busy, setBusy] = useState(false)

  const picked = mode === 'topic' && source === 'course' ? choices.find((c) => String(c.topic_id) === topicId) : null
  const reco = useRecommended(mode === 'topic' && difficulty === 'adaptive', picked ? picked.subject : subject, picked ? picked.topic : topic, picked?.topic_id)
  const grouped = useMemo(() => {
    const g = new Map()
    choices.forEach((c) => {
      const k = `${c.course} · ${c.subject}`
      if (!g.has(k)) g.set(k, [])
      g.get(k).push(c)
    })
    return [...g.entries()]
  }, [choices])

  const refWords = words(reference)
  const submit = async (e) => {
    e.preventDefault()
    if (docBusy) return
    const errs = {}
    if (mode === 'document') {
      if (!doc?.document_id) errs.document = 'Upload a PDF, DOCX, or TXT file first.'
    } else {
      if (source === 'free') {
        if (subject.trim().length < 2) errs.subject = 'Enter a subject (at least 2 characters).'
        if (topic.trim().length < 2) errs.topic = 'Enter a topic (at least 2 characters).'
      } else if (!picked) errs.topicId = 'Choose a topic.'
      if (refWords > 0 && refWords < 40) errs.reference = `Reference material needs at least 40 words (${refWords} so far), or leave it empty.`
    }
    const tl = timeLimit.trim() ? Number(timeLimit) : null
    if (tl != null && (!Number.isInteger(tl) || tl < 1 || tl > 180)) errs.timeLimit = 'Use a whole number of minutes from 1 to 180, or leave it empty.'
    setErrors(errs)
    if (Object.keys(errs).length) return

    const isDoc = mode === 'document'
    const body = isDoc ? {
      source_mode: 'document',
      subject: '',
      topic: docFocus.trim(),
      topic_id: null,
      unit: null,
      question_count: Number(count),
      difficulty,
      reference_text: null,
      document_id: doc.document_id,
      document_section: docSection || null,
      time_limit_min: tl,
      confidence_enabled: confidence,
    } : {
      source_mode: 'topic',
      subject: picked ? picked.subject : subject.trim(),
      topic: picked ? picked.topic : topic.trim(),
      topic_id: picked ? picked.topic_id : null,
      unit: picked ? picked.unit : unit.trim() || null,
      question_count: Number(count),
      difficulty,
      reference_text: reference.trim() || null,
      time_limit_min: tl,
      confidence_enabled: confidence,
    }
    setApiError(null)
    setBusy(true)
    try {
      const run = await studentApi.generatePractice(body)
      onStarted({
        runId: run.run_id,
        quizId: run.quiz_id,
        topic: isDoc ? (docFocus.trim() || docSection || doc.filename) : body.topic,
        note: run.difficulty_note,
      })
    } catch (ex) {
      setApiError(ex)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate className="stack-lg">
      <div className="field">
        <span className="field__label" id="st-gen-mode">Generation mode</span>
        <Segmented
          name="sourceMode"
          label="Generation mode"
          value={mode}
          onChange={setMode}
          options={[
            { value: 'topic', label: 'Topic / Text' },
            { value: 'document', label: 'Upload File' },
          ]}
        />
        <p className="field__hint">
          {mode === 'document'
            ? 'Practise from a PDF, DOCX, or TXT file you upload. Questions stay grounded in the file.'
            : 'Practise a course topic or any subject, with optional pasted notes.'}
        </p>
      </div>

      {mode === 'topic' ? (
        <>
          {hasChoices && (
            <div className="field">
              <span className="field__label" id="st-src">What to practise</span>
              <Segmented name="source" label="What to practise" value={source} onChange={setSource}
                options={[{ value: 'course', label: 'A topic from my courses' }, { value: 'free', label: 'Any subject and topic' }]} />
            </div>
          )}
          {source === 'course' && hasChoices ? (
            <Field label="Course topic" error={errors.topicId} hint={picked?.objectives?.length ? `Objectives: ${picked.objectives.map((o) => o.text).join('; ')}` : picked ? picked.unit : null}>
              {(p) => (
                <Select {...p} value={topicId} onChange={(e) => setTopicId(e.target.value)}>
                  {grouped.map(([g, items]) => (
                    <optgroup key={g} label={g}>{items.map((c) => <option key={c.topic_id} value={c.topic_id}>{c.topic} ({c.unit})</option>)}</optgroup>
                  ))}
                </Select>
              )}
            </Field>
          ) : (
            <div className="st-form-grid">
              <Field label="Subject" error={errors.subject}>
                {(p) => <Input {...p} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="e.g. DBMS" maxLength={160} />}
              </Field>
              <Field label="Topic" error={errors.topic}>
                {(p) => <Input {...p} value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="e.g. SQL joins" maxLength={160} />}
              </Field>
              <Field label="Syllabus unit (optional)" className="span-all">
                {(p) => <Input {...p} value={unit} onChange={(e) => setUnit(e.target.value)} placeholder="e.g. Unit 3: Relational queries" maxLength={160} />}
              </Field>
            </div>
          )}
        </>
      ) : (
        <div className="stack">
          <DocumentSourcePicker
            doc={doc}
            onDocChange={setDoc}
            section={docSection}
            onSectionChange={setDocSection}
            busy={docBusy}
            onBusyChange={setDocBusy}
            externalError={errors.document}
          />
          <Field
            label="Topic or chapter focus (optional)"
            hint="Optional keywords to focus questions on part of the file. Leave empty to cover the whole document."
          >
            {(p) => <Input {...p} value={docFocus} onChange={(e) => setDocFocus(e.target.value)} placeholder="e.g. Chapter 3, normalisation" maxLength={160} />}
          </Field>
          {doc && Number(count) > doc.recommended_max_questions && (
            <Alert tone="warning" title="Document length limit">
              This file supports up to about {doc.recommended_max_questions} questions ({doc.word_count.toLocaleString()} words).
              Fewer questions may be generated if the document does not have enough material for {count}.
            </Alert>
          )}
        </div>
      )}

      <div className="st-form-grid">
        <div className="field">
          <span className="field__label">Number of questions</span>
          <Segmented name="count" label="Number of questions" value={count} onChange={setCount} options={COUNTS.map((n) => ({ value: String(n), label: String(n) }))} />
        </div>
        <Field label="Time limit in minutes (optional)" error={errors.timeLimit} hint="Leave empty to practise without a timer.">
          {(p) => <Input {...p} type="number" inputMode="numeric" min={1} max={180} value={timeLimit} onChange={(e) => setTimeLimit(e.target.value)} placeholder="No limit" />}
        </Field>
      </div>

      <div className="field">
        <span className="field__label">Difficulty</span>
        <Segmented name="difficulty" label="Difficulty" value={difficulty} onChange={setDifficulty}
          options={DIFFS.map((d) => ({ value: d, label: DIFFICULTY_TEXT[d] }))} />
        <p className="field__hint">{DIFF_HINT[difficulty]}</p>
        {difficulty === 'adaptive' && (
          <div className="st-reco-diff" aria-live="polite">
            <Info size={15} aria-hidden="true" />
            {mode === 'document'
              ? <span className="muted">Adapts difficulty when linked to your mastery or uses balanced document difficulty.</span>
              : reco.loading ? <span className="muted">Checking your mastery on this topic…</span>
                : reco.data ? <span><strong>{DIFFICULTY_TEXT[reco.data.difficulty] || reco.data.difficulty}</strong> for you right now. {reco.data.reason}</span>
                  : reco.error ? <span className="muted">{reco.error.message}</span>
                    : <span className="muted">Enter a subject and topic to see the recommended level.</span>}
          </div>
        )}
      </div>

      {mode === 'topic' && (
        <Field label="Reference material (optional)" error={errors.reference}
          hint={`Paste notes or a textbook passage (at least 40 words) and the questions will be grounded in it. ${refWords ? `${refWords} words.` : ''}`}>
          {(p) => <Textarea {...p} value={reference} onChange={(e) => setReference(e.target.value)} rows={5} maxLength={12000} placeholder="Optional. Leave empty to let the model write study notes for the topic first." />}
        </Field>
      )}

      <Checkbox label="Ask me how confident I am before checking each answer" checked={confidence} onChange={(e) => setConfidence(e.target.checked)} />

      {apiError && <Alert tone="error" title="Could not start generating">{apiError.message}</Alert>}
      <div className="row">
        <Button type="submit" variant="primary" size="lg" icon={Sparkles} loading={busy} disabled={!!disabledReason || docBusy}>Generate practice quiz</Button>
        {disabledReason && <span className="muted st-small">{disabledReason}</span>}
      </div>
    </form>
  )
}

function RunPanel({ stored, onClear, onFinished }) {
  const { run, error, cancel, active } = useGenerationRun(stored.runId)
  const [cancelling, setCancelling] = useState(false)
  const [starting, setStarting] = useState(false)
  const [startErr, setStartErr] = useState(null)
  const navigate = useNavigate()
  const finished = run && !active
  useEffect(() => { if (finished) onFinished() }, [finished]) // eslint-disable-line react-hooks/exhaustive-deps
  const doCancel = async () => {
    setCancelling(true)
    try { await cancel() } catch (e) { setStartErr(e) } finally { setCancelling(false) }
  }
  const start = async () => {
    setStarting(true)
    setStartErr(null)
    try {
      const s = await studentApi.start(run.quiz_id || stored.quizId)
      safeSession.del(RUN_KEY)
      navigate(`/student/attempts/${s.session_id}`)
    } catch (e) {
      setStartErr(e)
      setStarting(false)
    }
  }
  const usable = finished && run.ready > 0
  return (
    <Card variant="elevated" className="st-run" title={`${finished ? (usable ? 'Ready' : 'Stopped') : 'Generating'}: ${stored.topic}`}
      subtitle="AI-generated practice. Questions are checked automatically but not reviewed by a lecturer."
      actions={finished ? <Button size="sm" variant="ghost" icon={X} onClick={onClear}>Dismiss</Button> : null}>
      <div className="stack">
        {(run?.difficulty_note || stored.note) && <p className="st-small muted"><Info size={13} aria-hidden="true" className="st-inline-icon" /> {run?.difficulty_note || stored.note}</p>}
        {run ? <GenerationProgress run={run} onCancel={active ? doCancel : null} cancelling={cancelling} showQuality={false} />
          : error ? <Alert tone="error">{error.message}</Alert> : <LoadingBlock rows={1} label="Loading progress" />}
        {error && run && <Alert tone="warning">Lost contact with the server; retrying. {error.message}</Alert>}
        {startErr && <Alert tone="error">{startErr.message}</Alert>}
        {usable && (
          <div className="row">
            <Button variant="teal" size="lg" icon={Play} onClick={start} loading={starting}>Start the quiz ({run.ready} questions)</Button>
            <Button variant="ghost" icon={RotateCcw} onClick={onClear}>Make another</Button>
          </div>
        )}
        {finished && !usable && <Button variant="secondary" icon={RotateCcw} onClick={onClear}>Try again</Button>}
      </div>
    </Card>
  )
}

function readRunFromParams(params) {
  const runIdParam = Number(params?.get('run_id'))
  if (Number.isInteger(runIdParam) && runIdParam > 0) {
    return {
      runId: runIdParam,
      quizId: null,
      topic: params.get('topic') || 'Recommended practice',
      note: null,
    }
  }
  return readRun()
}

export default function Practice() {
  const choices = useApi(() => topicsApi.choices(), [])
  const past = useApi(() => studentApi.practiceQuizzes(), [])
  const health = useModelHealth()
  const [searchParams] = useSearchParams()
  const urlRunId = searchParams.get('run_id')
  const [stored, setStored] = useState(() => readRunFromParams(searchParams))
  const { notify } = useToast()

  useEffect(() => {
    const rid = Number(urlRunId)
    if (!Number.isInteger(rid) || rid <= 0) return
    setStored((prev) => {
      const next = prev?.runId === rid ? prev : {
        runId: rid,
        quizId: null,
        topic: searchParams.get('topic') || 'Recommended practice',
        note: null,
      }
      safeSession.set(RUN_KEY, JSON.stringify(next))
      return next
    })
  }, [urlRunId, searchParams])

  const onStarted = (s) => {
    safeSession.set(RUN_KEY, JSON.stringify(s))
    setStored(s)
    notify('Generation started. You can leave this page; progress is kept.', 'info')
  }
  const clear = () => { safeSession.del(RUN_KEY); setStored(null) }
  const disabledReason = health.state === 'offline' ? 'The AI model is offline right now.' : health.state === 'loading' ? 'The AI model is still loading.' : null

  return (
    <div className="st-page stack-lg">
      <PageHeader eyebrow="Practice Lab" title="Practise any topic"
        subtitle="Generate a personal quiz. Practice scores are kept separate from your assessment grades." />
      <div className="st-practice">
        <div className="stack-lg">
          {stored && <RunPanel key={stored.runId} stored={stored} onClear={clear} onFinished={past.reload} />}
          <Card title="New practice quiz" subtitle="Questions are written by the AI model and checked automatically. A lecturer does not review them.">
            {choices.loading && !choices.data ? <LoadingBlock rows={3} label="Loading topics" /> : (
              <>
                {choices.error && <div style={{ marginBottom: 16 }}><Alert tone="warning">Could not load your course topics ({choices.error.message}). You can still type any topic.</Alert></div>}
                <PracticeForm key={choices.data ? 'loaded' : 'none'} choices={choices.data || []} onStarted={onStarted}
                  disabledReason={disabledReason} />
              </>
            )}
          </Card>
        </div>
        <Card title="Your practice quizzes" subtitle="AI-generated, not lecturer-reviewed">
          {past.loading && !past.data ? <LoadingBlock rows={3} /> : past.error ? <ErrorState error={past.error} onRetry={past.reload} /> : past.data.length ? (
            <ul className="st-quizlist st-quizlist--compact">{past.data.map((q) => <QuizListItem key={q.id} quiz={q} />)}</ul>
          ) : (
            <EmptyState icon={FlaskConical} title="No practice quizzes yet">Generate your first one with the form. Progress is shown live while the model writes the questions.</EmptyState>
          )}
        </Card>
      </div>
    </div>
  )
}
