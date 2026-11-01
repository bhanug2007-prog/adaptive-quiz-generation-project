import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle, Archive, ArrowDown, ArrowLeft, ArrowUp, BookOpen, CheckCircle2, Clock, Eye, Library, MinusCircle, Plus,
  Rocket, Send, Sparkles, Trash2, Undo2,
} from 'lucide-react'
import { lecturerApi, topicsApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { useGenerationRun } from '../../hooks/useGenerationRun'
import GenerationProgress from '../../components/quiz/GenerationProgress'
import {
  Alert, Badge, Button, Card, Checkbox, ConfirmDialog, Dialog, EmptyState, ErrorState, Input, LoadingBlock, PageHeader,
  ProgressBar, Tabs, useToast,
} from '../../components/ui'
import { DIFFICULTY_TEXT, dateTime, plural } from '../../utils/format'
import QuestionReview from '../../components/lecturer/QuestionReview'
import QuizSettingsForm from '../../components/lecturer/QuizSettingsForm'
import QuizExport from '../../components/lecturer/QuizExport'
import Stepper from '../../components/lecturer/Stepper'
import { FEEDBACK_TEXT, LATE_TEXT, QUIZ_STATUS, errText } from '../../components/lecturer/util'

const TABS = [
  { id: 'review', label: 'Questions' },
  { id: 'settings', label: 'Settings' },
  { id: 'publish', label: 'Preview & publish' },
  { id: 'export', label: 'Reports & export' },
]
const STEP_OF = { review: 2, settings: 3, publish: 4 }
const TAB_OF = { 2: 'review', 3: 'settings', 4: 'publish' }
const regenKey = (quizId) => `aiq.lecturer.regen.${quizId}`

export default function QuizDetail() {
  const { quizId } = useParams()
  const [sp, setSp] = useSearchParams()
  const tab = TABS.some((t) => t.id === sp.get('step')) ? sp.get('step') : 'review'
  const setTab = (t) => setSp((p) => { const n = new URLSearchParams(p); n.set('step', t); return n }, { replace: true })
  const d = useApi(() => lecturerApi.quiz(quizId), [quizId])
  const navigate = useNavigate()
  const { notify } = useToast()
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState(false)

  if (d.loading && !d.data) return <LoadingBlock rows={4} label="Loading quiz" />
  if (d.error && !d.data) return <ErrorState error={d.error} onRetry={d.reload} />
  const quiz = d.data
  const st = QUIZ_STATUS[quiz.status] || { text: quiz.status }
  const approved = quiz.review_counts?.approved || 0
  const draft = quiz.status === 'draft'

  const action = async (fn, ok, after) => {
    setBusy(true)
    try {
      const r = await fn()
      if (r && r.id) d.setData(r)
      notify(ok)
      setConfirm(null)
      after?.()
    } catch (e) {
      notify(errText(e), 'error')
      setConfirm(null)
    } finally {
      setBusy(false)
    }
  }
  const releasable = quiz.status === 'published' && !quiz.feedback_released && quiz.feedback_release !== 'immediate'

  return (
    <div className="lc-page">
      <Link to="/lecturer/quizzes" className="lc-back"><ArrowLeft size={14} aria-hidden="true" /> All quizzes</Link>
      <PageHeader eyebrow={[...new Set([quiz.course_title, quiz.subject_name].filter(Boolean))].join(' · ')} title={quiz.title}
        subtitle={<span className="row" style={{ gap: 8 }}>
          <Badge tone={st.tone}>{st.text}</Badge>
          <span>{plural(quiz.question_count, 'question')} · {quiz.max_marks} marks</span>
          {quiz.topics?.length > 0 && <span className="faint">{quiz.topics.join(', ')}</span>}
          {quiz.published_at && <span className="faint">Published {dateTime(quiz.published_at)}</span>}
        </span>}
        actions={<>
          {quiz.status === 'published' && <Button icon={Undo2} onClick={() => setConfirm('unpublish')}>Unpublish</Button>}
          {releasable && <Button variant="teal" icon={Send} onClick={() => setConfirm('release')}>Release feedback</Button>}
          {quiz.status !== 'archived' && quiz.status !== 'generating' && <Button variant="ghost" icon={Archive} onClick={() => setConfirm('archive')}>Archive</Button>}
          {(draft || quiz.status === 'archived') && <Button variant="ghost" icon={Trash2} onClick={() => setConfirm('delete')}>Delete</Button>}
        </>} />

      {draft && <Stepper current={STEP_OF[tab] ?? 4} onStep={(i) => setTab(TAB_OF[i])} enabled={(i) => i >= 2} />}
      {quiz.status === 'generating' && <Alert tone="info" title="Still generating">Questions are being generated. Follow progress on the <Link className="link" to="/lecturer/create">Create Quiz</Link> page.</Alert>}
      {draft && approved < quiz.question_count && (
        <div className="lc-review-progress">
          <span className="lc-small">{approved} of {quiz.question_count} approved</span>
          <ProgressBar value={approved} max={quiz.question_count || 1} label="Questions approved" />
        </div>
      )}

      <Tabs label="Quiz sections" value={tab} onChange={setTab} tabs={TABS} />
      <div className="lc-tabpanel" role="tabpanel" key={tab}>
        {tab === 'review' && <ItemsPanel quiz={quiz} setQuiz={d.setData} reload={d.reload} onNext={() => setTab('settings')} />}
        {tab === 'settings' && (
          <QuizSettingsForm key={quiz.id + String(quiz.status)} quiz={quiz} onSave={async (body) => {
            if (!body) { notify('Nothing changed', 'info'); return }
            d.setData(await lecturerApi.updateQuiz(quiz.id, body))
            notify('Settings saved')
            if (draft) setTab('publish')
          }} />
        )}
        {tab === 'publish' && <PublishPanel quiz={quiz} setQuiz={d.setData} goTo={setTab} />}
        {tab === 'export' && <QuizExport quiz={quiz} />}
      </div>

      <ConfirmDialog open={confirm === 'unpublish'} onClose={() => setConfirm(null)} loading={busy} confirmLabel="Unpublish" title="Unpublish this quiz?"
        onConfirm={() => action(() => lecturerApi.unpublish(quiz.id), 'Moved back to draft')}>
        <p className="muted">Students stop seeing it. This only works while nobody has started it; otherwise archive it.</p>
      </ConfirmDialog>
      <ConfirmDialog open={confirm === 'release'} onClose={() => setConfirm(null)} loading={busy} confirmLabel="Release feedback" tone="teal" title="Release feedback now?"
        onConfirm={() => action(() => lecturerApi.releaseFeedback(quiz.id), 'Feedback released to students')}>
        <p className="muted">Students who submitted can see the correct answers and explanations. This cannot be taken back.</p>
      </ConfirmDialog>
      <ConfirmDialog open={confirm === 'archive'} onClose={() => setConfirm(null)} loading={busy} confirmLabel="Archive" title="Archive this quiz?"
        onConfirm={() => action(() => lecturerApi.archive(quiz.id), 'Quiz archived')}>
        <p className="muted">Students can no longer start it. Results and reports are kept.</p>
      </ConfirmDialog>
      <ConfirmDialog open={confirm === 'delete'} onClose={() => setConfirm(null)} loading={busy} confirmLabel="Delete quiz" tone="danger" title="Delete this quiz?"
        onConfirm={() => action(() => lecturerApi.deleteQuiz(quiz.id), 'Quiz deleted', () => navigate('/lecturer/quizzes'))}>
        <p className="muted">The quiz is removed. Its questions stay in your question bank. Quizzes with attempts cannot be deleted.</p>
      </ConfirmDialog>
    </div>
  )
}

/* ---------------- Questions (review step) ---------------- */

function readRegen(quizId) {
  try { return JSON.parse(sessionStorage.getItem(regenKey(quizId)) || 'null') } catch { return null }
}
function writeRegen(quizId, v) {
  try { if (v) sessionStorage.setItem(regenKey(quizId), JSON.stringify(v)); else sessionStorage.removeItem(regenKey(quizId)) } catch { /* storage unavailable */ }
}

function ItemsPanel({ quiz, setQuiz, reload, onNext }) {
  const { notify } = useToast()
  const topics = useApi(() => topicsApi.choices(), [])
  const [regen, setRegen] = useState(() => readRegen(quiz.id))      // {runId, questionId}
  const { run: regenRun, active: regenActive } = useGenerationRun(regen?.runId)
  const [busy, setBusy] = useState(null)
  const [removing, setRemoving] = useState(null)
  const [adding, setAdding] = useState(false)
  const draft = quiz.status === 'draft'
  const approved = quiz.review_counts?.approved || 0

  useEffect(() => {
    if (regen && regenRun && !regenActive) {
      if (regenRun.status === 'done') notify('New question generated. Review it below.')
      else notify(regenRun.error || 'Regeneration did not produce a question that passed the checks.', 'error')
      writeRegen(quiz.id, null)
      setRegen(null)
      reload()
    }
  }, [regen, regenRun, regenActive, quiz.id, reload, notify])

  const items = async (body, ok) => {
    setBusy(JSON.stringify(body))
    try {
      setQuiz(await lecturerApi.updateItems(quiz.id, body))
      if (ok) notify(ok)
      return true
    } catch (e) {
      notify(errText(e), 'error')
      return false
    } finally {
      setBusy(null)
    }
  }
  const move = (idx, dir) => {
    const order = quiz.items.map((i) => i.item_id)
    const j = idx + dir
    ;[order[idx], order[j]] = [order[j], order[idx]]
    items({ order })
  }
  const regenerate = async (q) => {
    setBusy(`regen-${q.id}`)
    try {
      const r = await lecturerApi.regenerate(q.id, quiz.id)
      const v = { runId: r.run_id, questionId: q.id }
      writeRegen(quiz.id, v)
      setRegen(v)
    } catch (e) {
      notify(errText(e), 'error')
    } finally {
      setBusy(null)
    }
  }
  const replaceQuestion = (nq) => setQuiz((z) => {
    const its = z.items.map((it) => (it.question.id === nq.id ? { ...it, question: nq } : it))
    const counts = {}
    its.forEach((it) => { counts[it.question.review_status] = (counts[it.question.review_status] || 0) + 1 })
    return { ...z, items: its, review_counts: counts }
  })
  const objectivesFor = (q) => (topics.data || []).find((t) => t.topic_id === q.topic_id)?.objectives || []

  if (!quiz.items.length) {
    return (
      <>
        <EmptyState icon={BookOpen} title="No questions in this quiz" action={draft && <Button icon={Library} onClick={() => setAdding(true)}>Add from the question bank</Button>}>
          {draft ? 'Add approved questions from your bank, or generate a new quiz.' : 'This quiz has no questions.'}
        </EmptyState>
        {adding && <AddFromBank quiz={quiz} onClose={() => setAdding(false)} onAdd={(ids) => items({ add_question_ids: ids }, `${plural(ids.length, 'question')} added`)} />}
      </>
    )
  }

  return (
    <div className="stack">
      <div className="row-between">
        <p className="muted lc-small">
          {draft
            ? 'Check each question, its options, the correct answer and the explanation. Approve the good ones, edit or regenerate the rest, and reject or remove anything wrong. Every question must be approved before publishing.'
            : 'The quiz is not a draft, so its questions cannot change here. Unpublish it (if nobody has started) to edit.'}
        </p>
        {draft && <Button icon={Library} onClick={() => setAdding(true)}>Add from bank</Button>}
      </div>
      {quiz.items.map((it, idx) => {
        const q = it.question
        const isRegen = regen && regen.questionId === q.id
        return (
          <div key={it.item_id} className="lc-item">
            {isRegen && (
              <Card variant="elevated" className="lc-regen" title="Regenerating this question">
                {regenRun ? <GenerationProgress run={regenRun} /> : <LoadingBlock rows={1} label="Starting" />}
              </Card>
            )}
            <QuestionReview q={q} index={idx + 1} objectives={objectivesFor(q)} readOnly={!draft} allowDelete={false}
              onChanged={replaceQuestion} onDuplicated={() => notify('The copy is in your question bank', 'info')}
              extra={draft && <>
                <Button size="sm" variant="primary" icon={Sparkles} onClick={() => regenerate(q)} loading={busy === `regen-${q.id}`}
                  disabled={!!regen || q.locked} title="Ask the model for a replacement question on the same topic and difficulty">Regenerate</Button>
                <span className="lc-marks">
                  <label htmlFor={`marks-${it.item_id}`} className="faint">Marks</label>
                  <Input id={`marks-${it.item_id}`} type="number" min={0.5} max={100} step="0.5" defaultValue={it.marks} key={`${it.item_id}-${it.marks}`}
                    onBlur={(e) => { const m = Number(e.target.value); if (m > 0 && m <= 100 && m !== it.marks) items({ marks: [{ item_id: it.item_id, marks: m }] }, 'Marks updated') }} />
                </span>
                <Button size="sm" variant="ghost" icon={ArrowUp} disabled={idx === 0 || !!busy} onClick={() => move(idx, -1)} aria-label={`Move question ${idx + 1} up`} />
                <Button size="sm" variant="ghost" icon={ArrowDown} disabled={idx === quiz.items.length - 1 || !!busy} onClick={() => move(idx, 1)} aria-label={`Move question ${idx + 1} down`} />
                <Button size="sm" variant="ghost" icon={MinusCircle} onClick={() => setRemoving(it)}>Remove</Button>
              </>} />
          </div>
        )
      })}
      {draft && (
        <div className="lc-sticky-next">
          <span className="lc-small">{approved === quiz.question_count ? <><CheckCircle2 size={14} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-2px', color: 'var(--success)' }} /> All {quiz.question_count} approved</> : `${quiz.question_count - approved} still to approve`}</span>
          <Button variant="primary" onClick={onNext}>Next: settings</Button>
        </div>
      )}
      <ConfirmDialog open={!!removing} onClose={() => setRemoving(null)} title="Remove this question from the quiz?" confirmLabel="Remove"
        loading={!!busy} onConfirm={async () => { if (await items({ remove_item_ids: [removing.item_id] }, 'Question removed from the quiz')) setRemoving(null) }}>
        <p className="muted">It stays in your question bank and can be added back.</p>
      </ConfirmDialog>
      {adding && <AddFromBank quiz={quiz} onClose={() => setAdding(false)} onAdd={(ids) => items({ add_question_ids: ids }, `${plural(ids.length, 'question')} added`)} />}
    </div>
  )
}

function AddFromBank({ quiz, onClose, onAdd }) {
  const [q, setQ] = useState('')
  const [picked, setPicked] = useState([])
  const [busy, setBusy] = useState(false)
  const list = useApi(() => lecturerApi.questions({ course_id: quiz.course_id, review_status: 'approved', q: q || undefined, page_size: 50 }), [quiz.course_id, q])
  const inQuiz = new Set(quiz.items.map((i) => i.question.id))
  const toggle = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]))
  return (
    <Dialog open onClose={onClose} wide title="Add questions from the bank" description="Approved questions from this course. Reused questions are tracked in question analytics."
      footer={<>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant="primary" icon={Plus} disabled={!picked.length} loading={busy}
          onClick={async () => { setBusy(true); const ok = await onAdd(picked); setBusy(false); if (ok) onClose() }}>Add {picked.length || ''}</Button>
      </>}>
      <div className="stack">
        <Input type="search" aria-label="Search approved questions" placeholder="Search question text or topic" value={q} onChange={(e) => setQ(e.target.value)} />
        {list.loading && <LoadingBlock rows={2} label="Loading questions" />}
        {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
        {list.data && (list.data.items.length === 0 ? <p className="muted">No approved questions in this course{q ? ' match' : ' yet'}.</p> : (
          <ul className="list-plain lc-pick">
            {list.data.items.map((x) => (
              <li key={x.id}>
                {inQuiz.has(x.id) ? (
                  <span className="lc-pick__in"><span>{x.text}</span><Badge>Already in quiz</Badge></span>
                ) : (
                  <Checkbox checked={picked.includes(x.id)} onChange={() => toggle(x.id)}
                    label={<span>{x.text} <span className="faint">· {x.topic_label} · {DIFFICULTY_TEXT[x.difficulty]}{x.used_in_quizzes ? ` · used in ${plural(x.used_in_quizzes, 'quiz', 'quizzes')}` : ''}</span></span>} />
                )}
              </li>
            ))}
          </ul>
        ))}
      </div>
    </Dialog>
  )
}

/* ---------------- Preview & publish ---------------- */

function PublishPanel({ quiz, setQuiz, goTo }) {
  const preview = useApi(() => lecturerApi.preview(quiz.id), [quiz.id, quiz.question_count])
  const { notify } = useToast()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [confirm, setConfirm] = useState(false)
  const approved = quiz.review_counts?.approved || 0
  const allApproved = quiz.question_count > 0 && approved === quiz.question_count
  const draft = quiz.status === 'draft'

  const publish = async () => {
    setBusy(true)
    setError(null)
    try {
      setQuiz(await lecturerApi.publish(quiz.id))
      notify('Quiz published. Students in the course can see it now.')
      setConfirm(false)
    } catch (e) {
      setError(errText(e))
      setConfirm(false)
    } finally {
      setBusy(false)
    }
  }

  const checks = [
    { ok: allApproved, text: allApproved ? `All ${quiz.question_count} questions approved` : `${approved} of ${quiz.question_count} questions approved`, go: 'review' },
    { ok: true, text: `Attempts: ${quiz.attempts_allowed} · Time limit: ${quiz.time_limit_min ? `${quiz.time_limit_min} min` : 'none'}`, go: 'settings' },
    { ok: true, text: `Opens ${quiz.opens_at ? dateTime(quiz.opens_at) : 'when published'} · ${quiz.due_at ? `Due ${dateTime(quiz.due_at)}` : 'No due date'}`, go: 'settings' },
    { ok: true, text: `Late submissions: ${LATE_TEXT[quiz.late_policy]}${quiz.late_policy === 'penalty' ? ` (${quiz.late_penalty_pct}% penalty)` : ''} · Feedback: ${FEEDBACK_TEXT[quiz.feedback_release]}`, go: 'settings' },
    { ok: !quiz.graded || quiz.weight_cap_pct == null || quiz.contribution_pct <= quiz.weight_cap_pct - (quiz.weight_used_elsewhere_pct || 0) + 1e-9, text: quiz.graded ? `Graded, contributes ${quiz.contribution_pct}% of ${quiz.subject_name || 'the subject'} (cap ${quiz.weight_cap_pct ?? '—'}%, ${quiz.weight_used_elsewhere_pct ?? 0}% used by other quizzes)` : 'Practice only, not graded', go: 'settings' },
  ]

  return (
    <div className="lc-publish">
      <div className="stack">
        <Card title="Before publishing">
          <ul className="list-plain lc-checks">
            {checks.map((c, i) => (
              <li key={i} data-ok={c.ok || undefined}>
                {c.ok ? <CheckCircle2 size={16} aria-hidden="true" /> : <AlertTriangle size={16} aria-hidden="true" />}
                <span>{c.text}</span>
                {draft && <button type="button" className="link lc-small" onClick={() => goTo(c.go)}>Change</button>}
              </li>
            ))}
          </ul>
          {error && <Alert tone="error" title="The quiz was not published">{error}</Alert>}
          {draft ? (
            <div className="stack" style={{ marginTop: 'var(--space-4)' }}>
              <Button variant="primary" size="lg" icon={Rocket} disabled={!allApproved} onClick={() => setConfirm(true)}>Publish to students</Button>
              {!allApproved && <p className="faint lc-small">Publishing unlocks when every question is approved. AI-generated questions are never published without your review.</p>}
              <p className="faint lc-small">Not ready yet? The quiz is saved as a draft automatically.</p>
            </div>
          ) : (
            <Alert tone={quiz.status === 'published' ? 'success' : 'info'}>
              {quiz.status === 'published' ? `Published ${dateTime(quiz.published_at)}. Students enrolled in ${quiz.course_title} can take it.` : `This quiz is ${quiz.status}.`}
            </Alert>
          )}
        </Card>
      </div>
      <Card title={<span className="row" style={{ gap: 8 }}><Eye size={16} aria-hidden="true" />Student preview</span>} subtitle="Exactly what a student receives. Answers are not shown to students.">
        {preview.loading && <LoadingBlock rows={3} label="Loading preview" />}
        {preview.error && <ErrorState error={preview.error} onRetry={preview.reload} />}
        {preview.data && (
          <div className="lc-preview">
            <div className="lc-preview__head">
              <h3>{preview.data.title}</h3>
              <p className="faint lc-small"><Clock size={12} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-1px' }} /> {preview.data.time_limit_min ? `${preview.data.time_limit_min} minutes` : 'No time limit'} · {preview.data.max_marks} marks{quiz.shuffle_questions ? ' · questions shuffled for each student' : ''}</p>
              {preview.data.instructions && <p className="muted">{preview.data.instructions}</p>}
            </div>
            <ol className="list-plain stack">
              {preview.data.questions.map((pq) => (
                <li key={pq.question_id} className="lc-preview__q">
                  <p className="faint lc-small">Question {pq.position} · {pq.marks} {pq.marks === 1 ? 'mark' : 'marks'}</p>
                  <p className="lc-preview__text">{pq.text}</p>
                  <ul className="list-plain lc-preview__opts">
                    {pq.options.map((o) => <li key={o.id}><span className="lc-q__letter" aria-hidden="true">{o.label}</span>{o.text}</li>)}
                  </ul>
                </li>
              ))}
            </ol>
          </div>
        )}
      </Card>
      <ConfirmDialog open={confirm} onClose={() => setConfirm(false)} onConfirm={publish} loading={busy} confirmLabel="Publish" title="Publish this quiz?">
        <p className="muted">Students enrolled in {quiz.course_title} will see it{quiz.opens_at ? ` from ${dateTime(quiz.opens_at)}` : ' straight away'}. You can unpublish it until someone starts it.</p>
      </ConfirmDialog>
    </div>
  )
}
