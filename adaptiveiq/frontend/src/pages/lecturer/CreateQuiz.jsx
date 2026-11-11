import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, BookOpen, Sparkles } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { useGenerationRun } from '../../hooks/useGenerationRun'
import { useModelHealth } from '../../hooks/useModelHealth'
import DocumentSourcePicker from '../../components/quiz/DocumentSourcePicker'
import GenerationProgress from '../../components/quiz/GenerationProgress'
import {
  Alert, Button, Card, Checkbox, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, Segmented, Select, Textarea, useToast,
} from '../../components/ui'
import Stepper from '../../components/lecturer/Stepper'
import { CourseGate, useCourses } from '../../components/lecturer/CoursePicker'
import { errText, rememberCourse, rememberedCourse, wordCount } from '../../components/lecturer/util'

export const RUN_KEY = 'aiq.lecturer.generation'
export const REF_MAX = 12000
const REF_MIN_WORDS = 40

export function readStoredRun() {
  try { return JSON.parse(sessionStorage.getItem(RUN_KEY) || 'null') } catch { return null }
}
function storeRun(v) {
  try { if (v) sessionStorage.setItem(RUN_KEY, JSON.stringify(v)); else sessionStorage.removeItem(RUN_KEY) } catch { /* storage unavailable */ }
}

export default function CreateQuiz() {
  const [stored, setStored] = useState(() => readStoredRun())
  const courses = useCourses()
  const navigate = useNavigate()
  const save = (v) => { storeRun(v); setStored(v) }

  return (
    <div className="lc-page">
      <PageHeader eyebrow="AI quiz builder" title="Create a quiz"
        subtitle="Pick a topic or upload study material, let the model draft questions, then review every one before it can be published." />
      <Stepper current={stored ? 1 : 0} />
      {stored ? (
        <GenerateStep stored={stored} onReset={() => save(null)}
          onReview={(quizId) => { save(null); navigate(`/lecturer/quizzes/${quizId}?step=review`) }} />
      ) : (
        <CourseGate courses={courses} emptyText="A quiz belongs to a course topic. Create a course with a subject, unit and topic first.">
          {(list) => <SetupStep courses={list} onStarted={save} />}
        </CourseGate>
      )}
    </div>
  )
}

function SetupStep({ courses, onStarted }) {
  const [courseId, setCourseId] = useState(() => {
    const r = rememberedCourse()
    return String((courses.find((c) => String(c.id) === r) || courses[0]).id)
  })
  const detail = useApi(() => lecturerApi.course(courseId), [courseId])
  const health = useModelHealth()
  const { notify } = useToast()
  const [v, setV] = useState({
    subject: '', unit: '', topic: '', objectives: [], title: '', count: '10', mode: 'mixed',
    dist: { easy: '3', medium: '4', hard: '3' }, sourceMode: 'topic', reference: '', focusTopic: '', duration: '', marks: '1',
  })
  const [doc, setDoc] = useState(null)
  const [docSection, setDocSection] = useState('')
  const [docBusy, setDocBusy] = useState(false)
  const [touched, setTouched] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k, val) => setV((s) => ({ ...s, [k]: val }))

  const subjects = detail.data?.subjects || []
  const subject = subjects.find((s) => String(s.id) === v.subject)
  const units = subject?.units || []
  const unit = units.find((u) => String(u.id) === v.unit)
  const topics = unit?.topics || []
  const topic = topics.find((t) => String(t.id) === v.topic)

  // Pick the first option at each level so the common case is one click.
  useEffect(() => {
    if (!detail.data) return
    setV((s) => {
      const sub = subjects.find((x) => String(x.id) === s.subject) || subjects[0]
      const un = sub?.units.find((x) => String(x.id) === s.unit) || sub?.units[0]
      const tp = un?.topics.find((x) => String(x.id) === s.topic) || un?.topics[0]
      const next = { ...s, subject: sub ? String(sub.id) : '', unit: un ? String(un.id) : '', topic: tp ? String(tp.id) : '' }
      if (next.topic !== s.topic) next.objectives = []
      return next
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail.data, v.subject, v.unit])

  const count = Number(v.count)
  const distTotal = ['easy', 'medium', 'hard'].reduce((a, k) => a + (Number(v.dist[k]) || 0), 0)
  const refWords = wordCount(v.reference)
  const problems = useMemo(() => {
    const p = {}
    if (!topic) p.topic = 'Choose a topic.'
    if (v.title.trim().length < 2) p.title = 'Give the quiz a title.'
    if (!(Number.isInteger(count) && count >= 1 && count <= 30)) p.count = 'Choose 1 to 30 questions.'
    if (v.mode === 'custom' && distTotal !== count) p.dist = `The mix adds up to ${distTotal}, not ${v.count || 0}.`
    if (v.sourceMode === 'document') {
      if (!doc?.document_id) p.document = 'Upload a PDF, DOCX, or TXT file first.'
    } else if (v.reference.trim() && refWords < REF_MIN_WORDS) {
      p.reference = `Reference material needs at least ${REF_MIN_WORDS} words (now ${refWords}), or leave it empty.`
    }
    if (v.duration && !(Number(v.duration) >= 1 && Number(v.duration) <= 300)) p.duration = 'Use 1 to 300 minutes.'
    if (!(Number(v.marks) > 0 && Number(v.marks) <= 100)) p.marks = 'Use a number above 0, up to 100.'
    return p
  }, [topic, v, count, distTotal, refWords, doc])
  const show = touched ? problems : {}

  const submit = async (e) => {
    e.preventDefault()
    setTouched(true)
    setError(null)
    if (docBusy || Object.keys(problems).length) return
    const isDoc = v.sourceMode === 'document'
    const body = {
      course_id: Number(courseId), subject_id: Number(v.subject), topic_id: Number(v.topic), title: v.title.trim(),
      question_count: count, difficulty: v.mode === 'custom' ? 'mixed' : v.mode,
      distribution: v.mode === 'custom' ? { easy: Number(v.dist.easy) || 0, medium: Number(v.dist.medium) || 0, hard: Number(v.dist.hard) || 0 } : null,
      source_mode: v.sourceMode,
      reference_text: isDoc ? null : (v.reference.trim() || null),
      document_id: isDoc ? doc.document_id : null,
      document_section: isDoc ? (docSection || null) : null,
      focus_topic: isDoc ? (v.focusTopic.trim() || null) : null,
      objective_ids: v.objectives.map(Number),
      target_duration_min: v.duration ? Number(v.duration) : null, marks_each: Number(v.marks),
    }
    setBusy(true)
    try {
      const run = await lecturerApi.generate(body)
      notify('Generation started')
      onStarted({ runId: run.run_id, quizId: run.quiz_id, title: body.title, topic: topic.name, docName: isDoc ? doc.filename : null })
    } catch (err) {
      setError(errText(err))
    } finally {
      setBusy(false)
    }
  }

  if (detail.loading && !detail.data) return <LoadingBlock rows={3} label="Loading course" />
  if (detail.error) return <ErrorState error={detail.error} onRetry={detail.reload} />
  const noTopics = !subjects.some((s) => s.units.some((u) => u.topics.length))

  return (
    <form className="stack-lg appear" onSubmit={submit} noValidate>
      <Card title="What is the quiz about?" subtitle="Course → subject → unit → topic. Questions are tagged with this topic for analytics.">
        <div className="lc-form-grid">
          <Field label="Course">
            {(a) => (
              <Select {...a} value={courseId} onChange={(e) => { rememberCourse(e.target.value); setCourseId(e.target.value); setV((s) => ({ ...s, subject: '', unit: '', topic: '', objectives: [] })) }}>
                {courses.map((c) => <option key={c.id} value={c.id}>{c.code} · {c.title}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Subject">
            {(a) => (
              <Select {...a} value={v.subject} onChange={(e) => setV((s) => ({ ...s, subject: e.target.value, unit: '', topic: '', objectives: [] }))} disabled={!subjects.length}>
                {!subjects.length && <option value="">No subjects</option>}
                {subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Unit">
            {(a) => (
              <Select {...a} value={v.unit} onChange={(e) => setV((s) => ({ ...s, unit: e.target.value, topic: '', objectives: [] }))} disabled={!units.length}>
                {!units.length && <option value="">No units</option>}
                {units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </Select>
            )}
          </Field>
          <Field label="Topic" error={show.topic}>
            {(a) => (
              <Select {...a} value={v.topic} onChange={(e) => setV((s) => ({ ...s, topic: e.target.value, objectives: [] }))} disabled={!topics.length}>
                {!topics.length && <option value="">No topics</option>}
                {topics.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </Select>
            )}
          </Field>
        </div>
        {noTopics && (
          <EmptyState icon={BookOpen} title="This course has no topics yet" action={<Button to={`/lecturer/courses/${courseId}`}>Add subjects and topics</Button>}>
            Add a subject, a unit and at least one topic to the course, then come back.
          </EmptyState>
        )}
        {topic && (
          <fieldset className="lc-fieldset" style={{ marginTop: 'var(--space-4)' }}>
            <legend className="field__label">Learning objectives (optional)</legend>
            {topic.objectives.length === 0 ? (
              <p className="faint lc-small">This topic has no learning objectives. You can add them on the course page.</p>
            ) : (
              <div className="stack" style={{ gap: 'var(--space-2)' }}>
                {topic.objectives.map((o) => (
                  <Checkbox key={o.id} label={o.text} checked={v.objectives.includes(String(o.id))}
                    disabled={!v.objectives.includes(String(o.id)) && v.objectives.length >= 10}
                    onChange={(e) => set('objectives', e.target.checked ? [...v.objectives, String(o.id)] : v.objectives.filter((x) => x !== String(o.id)))} />
                ))}
                <p className="faint lc-small">The model is asked to cover the objectives you tick.</p>
              </div>
            )}
          </fieldset>
        )}
      </Card>

      <Card title="Configure the questions">
        <div className="lc-form-grid">
          <Field label="Quiz title" error={show.title} className="span-all">
            {(a) => <Input {...a} value={v.title} onChange={(e) => set('title', e.target.value)} maxLength={200} placeholder={topic ? `${topic.name} quiz 1` : 'Quiz title'} />}
          </Field>
          <Field label="Number of questions" error={show.count} hint="1 to 30. The model takes a few seconds per question.">
            {(a) => <Input {...a} type="number" min={1} max={30} value={v.count} onChange={(e) => set('count', e.target.value)} />}
          </Field>
          <Field label="Marks per question" error={show.marks}>
            {(a) => <Input {...a} type="number" min={0.5} max={100} step="0.5" value={v.marks} onChange={(e) => set('marks', e.target.value)} />}
          </Field>
          <Field label="Target duration in minutes (optional)" error={show.duration} hint="A guide for the time limit you set later.">
            {(a) => <Input {...a} type="number" min={1} max={300} value={v.duration} onChange={(e) => set('duration', e.target.value)} />}
          </Field>
        </div>
        <div className="stack" style={{ marginTop: 'var(--space-4)' }}>
          <span className="field__label" id="diff-label">Difficulty</span>
          <Segmented name="difficulty" label="Difficulty" value={v.mode} onChange={(m) => set('mode', m)}
            options={[{ value: 'easy', label: 'Easy' }, { value: 'medium', label: 'Medium' }, { value: 'hard', label: 'Hard' }, { value: 'mixed', label: 'Mixed' }, { value: 'custom', label: 'Set the mix' }]} />
          {v.mode === 'custom' && (
            <div className="stack" style={{ gap: 'var(--space-2)' }}>
              <div className="lc-dist">
                {['easy', 'medium', 'hard'].map((k) => (
                  <Field key={k} label={k[0].toUpperCase() + k.slice(1)}>
                    {(a) => <Input {...a} type="number" min={0} max={30} value={v.dist[k]} onChange={(e) => set('dist', { ...v.dist, [k]: e.target.value })} />}
                  </Field>
                ))}
              </div>
              <p className={show.dist ? 'field__error' : 'faint lc-small'} role={show.dist ? 'alert' : undefined}>
                {show.dist || `Total ${distTotal} of ${v.count || 0} questions.`}
              </p>
            </div>
          )}
          {v.mode === 'mixed' && <p className="faint lc-small">A balanced spread of easy, medium and hard questions.</p>}
        </div>

        <div className="stack" style={{ marginTop: 'var(--space-5)', paddingTop: 'var(--space-4)', borderTop: '1px solid var(--border)' }}>
          <div className="field">
            <span className="field__label">Generation mode</span>
            <Segmented
              name="sourceMode"
              label="Generation mode"
              value={v.sourceMode}
              onChange={(m) => set('sourceMode', m)}
              options={[
                { value: 'topic', label: 'Topic / Text' },
                { value: 'document', label: 'Upload File' },
              ]}
            />
            <p className="field__hint">
              {v.sourceMode === 'document'
                ? 'Generate MCQs grounded strictly in an uploaded PDF, DOCX, or TXT document.'
                : 'Generate from the selected topic, optionally with pasted lecture notes or textbook excerpts.'}
            </p>
          </div>

          {v.sourceMode === 'topic' ? (
            <Field label="Reference material (optional)" error={show.reference}
              hint={`Paste lecture notes or a textbook passage (at least ${REF_MIN_WORDS} words). Questions are then checked against it. ${v.reference.length.toLocaleString()} / ${REF_MAX.toLocaleString()} characters.`}>
              {(a) => <Textarea {...a} rows={6} maxLength={REF_MAX} value={v.reference} onChange={(e) => set('reference', e.target.value)}
                placeholder="Without reference material the model first writes short study notes on the topic and grounds the questions in them." />}
            </Field>
          ) : (
            <div className="stack">
              <DocumentSourcePicker
                doc={doc}
                onDocChange={setDoc}
                section={docSection}
                onSectionChange={setDocSection}
                busy={docBusy}
                onBusyChange={setDocBusy}
                externalError={show.document}
              />
              <Field
                label="Topic or chapter focus (optional)"
                hint="Optional keywords to prioritise matching passages inside the uploaded document."
              >
                {(a) => (
                  <Input
                    {...a}
                    value={v.focusTopic}
                    onChange={(e) => set('focusTopic', e.target.value)}
                    maxLength={200}
                    placeholder={topic ? `e.g. ${topic.name}` : 'Optional focus topic'}
                  />
                )}
              </Field>
              {doc && Number.isInteger(count) && count > doc.recommended_max_questions && (
                <Alert tone="warning" title="More questions requested than document size">
                  This document supports up to about {doc.recommended_max_questions} grounded questions ({doc.word_count.toLocaleString()} words).
                  The generator may produce fewer than {count} questions if the document lacks enough supported material.
                </Alert>
              )}
            </div>
          )}
        </div>
      </Card>

      {health.state !== 'ok' && health.state !== 'checking' && (
        <Alert tone="warning" title="The AI model is not ready">
          {health.detail || 'The question generator cannot be reached right now.'} You can still try; the server will say if it cannot start.
        </Alert>
      )}
      {error && <Alert tone="error" title="Could not start generation">{error}</Alert>}
      {touched && Object.keys(problems).length > 0 && <Alert tone="error">Fix the highlighted fields first.</Alert>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <Button type="submit" variant="primary" size="lg" icon={Sparkles} loading={busy} disabled={noTopics || docBusy}>Generate questions</Button>
      </div>
    </form>
  )
}

function GenerateStep({ stored, onReset, onReview }) {
  const { run, error, cancel, active } = useGenerationRun(stored.runId)
  const [cancelling, setCancelling] = useState(false)
  const { notify } = useToast()
  const finished = run && !active
  const usable = run && (run.status === 'done' || run.status === 'partial') && run.ready > 0
  const doCancel = async () => {
    setCancelling(true)
    try { await cancel() } catch (e) { notify(errText(e), 'error') } finally { setCancelling(false) }
  }
  return (
    <Card className="appear" title={`Generating “${stored.title}”`}
      subtitle={`${stored.topic}${stored.docName ? ` · ${stored.docName}` : ''}. Every question goes through format, duplicate, grounding and answer checks; failed outputs are retried automatically. You can leave this page and come back.`}>
      {!run && !error && <LoadingBlock rows={2} label="Connecting to the generation run" />}
      {error && !run && (
        <ErrorState error={error} title="Could not load the generation run"
          onRetry={undefined} />
      )}
      {run && <GenerationProgress run={run} onCancel={active ? doCancel : undefined} cancelling={cancelling} />}
      {error && run && <p className="faint lc-small">Lost contact with the server for a moment, retrying…</p>}
      {finished && (
        <div className="row" style={{ justifyContent: 'flex-end', marginTop: 'var(--space-5)' }}>
          {!usable && <Alert tone="error">{run.status === 'cancelled' ? 'Generation was cancelled.' : run.error || 'No question passed the checks.'} Change the settings and try again.</Alert>}
          <Button variant="ghost" onClick={onReset}>{usable ? 'Start another quiz' : 'Back to setup'}</Button>
          {usable && <Button variant="primary" iconRight={ArrowRight} onClick={() => onReview(run.quiz_id || stored.quizId)}>Review {run.ready} questions</Button>}
        </div>
      )}
      {error && !run && <div className="row" style={{ justifyContent: 'flex-end' }}><Button onClick={onReset}>Back to setup</Button></div>}
    </Card>
  )
}
