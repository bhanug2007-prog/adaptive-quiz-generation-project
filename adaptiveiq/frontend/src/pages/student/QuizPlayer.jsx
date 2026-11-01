import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import {
  AlertTriangle, Check, CheckCircle2, ChevronLeft, ChevronRight, CloudOff, Eraser, Flag, Loader2, Send, Timer, XCircle,
} from 'lucide-react'
import { Alert, Badge, Button, ConfirmDialog, ErrorState, LoadingBlock, ProgressBar } from '../../components/ui'
import { studentApi } from '../../api/endpoints'
import { DIFFICULTY_TEXT, plural } from '../../utils/format'
import { KindBadge } from '../../components/student/Badges'
import { safeSession } from '../../components/student/helpers'

const CONFIDENCE = [{ v: 1, label: 'Guessing' }, { v: 2, label: 'Unsure' }, { v: 3, label: 'Sure' }]
const KEY_INDEX = { 1: 0, 2: 1, 3: 2, 4: 3, a: 0, b: 1, c: 2, d: 3 }

function fmtClock(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${r}` : `${m}:${r}`
}

const isTimeUp = (e) => e?.status === 409 && /time is up|already been submitted/i.test(e.message || '')

/** Countdown driven by the server's deadline, corrected for the difference between server and browser clocks. */
function useCountdown(deadlineAt, serverNow) {
  const offset = useMemo(() => (serverNow ? new Date(serverNow).getTime() - Date.now() : 0), [serverNow])
  const end = deadlineAt ? new Date(deadlineAt).getTime() : null
  const [left, setLeft] = useState(() => (end ? end - (Date.now() + offset) : null))
  useEffect(() => {
    if (!end) return undefined
    const tick = () => setLeft(end - (Date.now() + offset))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [end, offset])
  return left
}

function Timerbox({ left, total }) {
  const [announce, setAnnounce] = useState('')
  const said = useRef(new Set())
  useEffect(() => {
    if (left == null) return
    for (const [ms, text] of [[300000, '5 minutes left'], [60000, '1 minute left']]) {
      if (left <= ms && left > ms - 5000 && !said.current.has(ms)) { said.current.add(ms); setAnnounce(text) }
    }
  }, [left])
  if (left == null) return null
  const tone = left <= 60000 ? 'danger' : left <= 300000 ? 'warn' : ''
  return (
    <div className={`st-timer ${tone ? `st-timer--${tone}` : ''}`} title={total ? `Time limit ${Math.round(total / 60000)} minutes` : undefined}>
      <Timer size={16} aria-hidden="true" />
      <span className="num" aria-label={`Time left ${fmtClock(left)}`}>{fmtClock(left)}</span>
      <span className="visually-hidden" aria-live="assertive">{announce}</span>
    </div>
  )
}

function SaveStatus({ status, onRetry }) {
  return (
    <div className={`st-save st-save--${status.kind}`} aria-live="polite">
      {status.kind === 'saving' && <><Loader2 size={14} className="st-spin" aria-hidden="true" /><span>Saving…</span></>}
      {status.kind === 'saved' && <><Check size={14} aria-hidden="true" /><span>All answers saved</span></>}
      {status.kind === 'idle' && <><Check size={14} aria-hidden="true" /><span>Answers save automatically</span></>}
      {status.kind === 'error' && (
        <>
          <CloudOff size={14} aria-hidden="true" />
          <span>{status.count === 1 ? 'An answer is not saved' : `${status.count} answers are not saved`}</span>
          <button type="button" className="st-save__retry" onClick={onRetry}>Retry</button>
        </>
      )}
    </div>
  )
}

export default function QuizPlayer() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const flagKey = `aiq.student.flags.${sessionId}`

  const [attempt, setAttempt] = useState(null)
  const [loadErr, setLoadErr] = useState(null)
  const [answers, setAnswers] = useState({})          // qid -> {option_id, confidence, checked}
  const [saveState, setSaveState] = useState({})      // qid -> saving | saved | error
  const [checks, setChecks] = useState({})            // qid -> {correct_option_id, is_correct, explanation}
  const [checking, setChecking] = useState(null)
  const [actionErr, setActionErr] = useState(null)
  const [idx, setIdx] = useState(0)
  const [flags, setFlags] = useState(() => { try { return JSON.parse(safeSession.get(flagKey) || '[]') } catch { return [] } })
  const [confirm, setConfirm] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [timeUp, setTimeUp] = useState(false)

  const answersRef = useRef({})
  const inflight = useRef({})
  const pending = useRef({})
  const timeSpent = useRef({})                         // qid -> seconds already counted
  const segStart = useRef(null)                        // when the current question came on screen
  const submittedRef = useRef(false)

  const load = useCallback(async () => {
    setLoadErr(null)
    try {
      const a = await studentApi.attempt(sessionId)
      if (a.status !== 'in_progress') { navigate(`/student/attempts/${sessionId}/result`, { replace: true }); return }
      const init = {}
      Object.entries(a.answers || {}).forEach(([k, v]) => {
        init[k] = { option_id: v.option_id, confidence: v.confidence, checked: v.checked }
        timeSpent.current[k] = v.time_spent_s || 0
      })
      answersRef.current = init
      setAnswers(init)
      setAttempt(a)
      const firstOpen = a.questions.findIndex((q) => !init[q.question_id]?.option_id)
      setIdx(firstOpen > 0 ? firstOpen : 0)
      segStart.current = Date.now()
      // A checked practice answer is locked; ask again for its key so the feedback shows after a refresh.
      const checked = Object.entries(init).filter(([, v]) => v.checked && v.option_id)
      if (a.can_check_answers && checked.length) {
        const res = await Promise.allSettled(checked.map(([k]) => studentApi.checkAnswer(sessionId, k)))
        const c = {}
        res.forEach((r, i) => { if (r.status === 'fulfilled') c[checked[i][0]] = r.value })
        setChecks(c)
      }
    } catch (e) {
      setLoadErr(e)
    }
  }, [sessionId, navigate])
  useEffect(() => { load() }, [load])

  const questions = attempt?.questions || []
  const q = questions[idx]
  const qid = q ? String(q.question_id) : null

  /* ---------- time spent per question ---------- */
  const elapsedFor = useCallback((id) => {
    let t = timeSpent.current[id] || 0
    if (id === qid && segStart.current && document.visibilityState !== 'hidden') t += (Date.now() - segStart.current) / 1000
    return Math.round(t * 10) / 10
  }, [qid])
  const closeSegment = useCallback(() => {
    if (qid && segStart.current) timeSpent.current[qid] = (timeSpent.current[qid] || 0) + (Date.now() - segStart.current) / 1000
    segStart.current = Date.now()
  }, [qid])
  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === 'hidden') closeSegment()
      else segStart.current = Date.now()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [closeSegment])

  /* ---------- finishing ---------- */
  const goResult = useCallback(() => {
    submittedRef.current = true
    safeSession.del(flagKey)
    navigate(`/student/attempts/${sessionId}/result`, { replace: true })
  }, [navigate, sessionId, flagKey])

  /* ---------- autosave: one request per question at a time, latest value wins ---------- */
  const send = useCallback(async (id) => {
    if (inflight.current[id] || submittedRef.current) return
    const body = pending.current[id]
    if (!body) return
    delete pending.current[id]
    inflight.current[id] = true
    let failed = false
    setSaveState((s) => ({ ...s, [id]: 'saving' }))
    try {
      let tries = 0
      for (;;) {
        try {
          await studentApi.saveAnswer(sessionId, id, body)
          break
        } catch (e) {
          if (isTimeUp(e)) { setTimeUp(true); goResult(); return }
          if (e.status && e.status !== 0 && e.status < 500) throw e
          if (++tries >= 3) throw e
          await new Promise((r) => setTimeout(r, 600 * tries))
        }
      }
      setSaveState((s) => ({ ...s, [id]: pending.current[id] ? 'saving' : 'saved' }))
    } catch (e) {
      failed = true
      if (!pending.current[id]) pending.current[id] = body
      setSaveState((s) => ({ ...s, [id]: 'error' }))
      if (e.status === 409 || e.status === 422) setActionErr(e)
    } finally {
      inflight.current[id] = false
      if (!failed && pending.current[id] && !submittedRef.current) send(id)
    }
  }, [sessionId, goResult])
  const saveStateRef = useRef(saveState)
  saveStateRef.current = saveState

  const queueSave = useCallback((id, next) => {
    answersRef.current = { ...answersRef.current, [id]: { ...answersRef.current[id], ...next } }
    setAnswers(answersRef.current)
    const a = answersRef.current[id]
    pending.current[id] = { option_id: a.option_id ?? null, confidence: a.confidence ?? null, time_spent_s: elapsedFor(id) }
    setSaveState((s) => ({ ...s, [id]: 'saving' }))
    send(id)
  }, [send, elapsedFor])

  const retryAll = useCallback(() => {
    Object.keys(pending.current).forEach((id) => { if (!inflight.current[id]) send(id) })
  }, [send])
  useEffect(() => {
    window.addEventListener('online', retryAll)
    return () => window.removeEventListener('online', retryAll)
  }, [retryAll])

  const failedCount = Object.values(saveState).filter((s) => s === 'error').length
  const savingCount = Object.values(saveState).filter((s) => s === 'saving').length
  const status = failedCount ? { kind: 'error', count: failedCount } : savingCount ? { kind: 'saving' } : Object.keys(saveState).length ? { kind: 'saved' } : { kind: 'idle' }

  useEffect(() => {
    const warn = (e) => { if (Object.keys(pending.current).length || savingCount) { e.preventDefault(); e.returnValue = '' } }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [savingCount])

  /* ---------- answer actions ---------- */
  const locked = qid ? !!(answers[qid]?.checked || checks[qid]) : false
  const choose = useCallback((optionId) => {
    if (!qid || locked || submittedRef.current) return
    setActionErr(null)
    queueSave(qid, { option_id: optionId })
  }, [qid, locked, queueSave])
  const clear = () => { if (!locked) queueSave(qid, { option_id: null }) }
  const setConfidence = (v) => {
    if (locked) return
    const cur = answersRef.current[qid]
    const nextV = cur?.confidence === v ? null : v
    if (cur?.option_id) queueSave(qid, { confidence: nextV })
    else {
      answersRef.current = { ...answersRef.current, [qid]: { ...cur, confidence: nextV } }
      setAnswers(answersRef.current)
    }
  }

  const waitForSaves = async () => {
    for (let i = 0; i < 40 && (Object.values(inflight.current).some(Boolean)); i++) await new Promise((r) => setTimeout(r, 100))
  }

  const check = async () => {
    if (!answers[qid]?.option_id) return
    setChecking(qid)
    setActionErr(null)
    try {
      if (pending.current[qid] || inflight.current[qid]) {
        send(qid)
        await waitForSaves()
      }
      if (saveStateRef.current[qid] === 'error') throw new Error('Your answer is not saved yet. Retry saving, then check.')
      const r = await studentApi.checkAnswer(sessionId, qid)
      setChecks((c) => ({ ...c, [qid]: r }))
      answersRef.current = { ...answersRef.current, [qid]: { ...answersRef.current[qid], checked: true } }
      setAnswers(answersRef.current)
    } catch (e) {
      if (isTimeUp(e)) goResult()
      else setActionErr(e)
    } finally {
      setChecking(null)
    }
  }

  const go = useCallback((n) => {
    if (n < 0 || n >= questions.length) return
    closeSegment()
    setIdx(n)
  }, [questions.length, closeSegment])

  const toggleFlag = () => {
    setFlags((f) => {
      const next = f.includes(qid) ? f.filter((x) => x !== qid) : [...f, qid]
      safeSession.set(flagKey, JSON.stringify(next))
      return next
    })
  }

  const doSubmit = useCallback(async () => {
    if (submittedRef.current) return
    setSubmitting(true)
    setActionErr(null)
    try {
      Object.keys(pending.current).forEach((id) => send(id))
      await waitForSaves()
      submittedRef.current = true
      await studentApi.submit(sessionId)
      goResult()
    } catch (e) {
      if (isTimeUp(e) || e.status === 409) { goResult(); return }
      submittedRef.current = false
      setActionErr(e)
      setSubmitting(false)
      setConfirm(false)
    }
  }, [sessionId, send, goResult])

  /* ---------- timer ---------- */
  const left = useCountdown(attempt?.deadline_at, attempt?.server_now)
  useEffect(() => {
    if (left != null && left <= 0 && attempt && !submittedRef.current && !timeUp) {
      setTimeUp(true)
      setConfirm(false)
      doSubmit()
    }
  }, [left, attempt, timeUp, doSubmit])

  /* ---------- keyboard ---------- */
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey || confirm) return
      const tag = e.target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target?.isContentEditable) return
      if (e.key === 'ArrowRight') { e.preventDefault(); go(idx + 1); return }
      if (e.key === 'ArrowLeft') { e.preventDefault(); go(idx - 1); return }
      const k = KEY_INDEX[e.key.toLowerCase()]
      if (k != null && q?.options[k]) { e.preventDefault(); choose(q.options[k].id) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go, idx, q, choose, confirm])

  /* ---------- render ---------- */
  if (loadErr) return <ErrorState error={loadErr} onRetry={load} title={loadErr.status === 404 ? 'Attempt not found' : 'Could not load this attempt'} />
  if (!attempt) return <LoadingBlock rows={4} label="Loading your quiz" />

  const total = questions.length
  const answeredCount = questions.filter((x) => answers[x.question_id]?.option_id).length
  const unanswered = total - answeredCount
  const a = answers[qid] || {}
  const chk = checks[qid]
  const isPractice = attempt.kind === 'practice'
  const totalMs = attempt.deadline_at ? new Date(attempt.deadline_at) - new Date(attempt.started_at) : null

  const optionState = (o) => {
    if (!chk) return a.option_id === o.id ? 'selected' : ''
    if (o.id === chk.correct_option_id) return 'correct'
    if (a.option_id === o.id) return 'wrong'
    return 'dim'
  }

  return (
    <div className="st-player">
      <header className="st-player__bar">
        <div className="st-player__title">
          <p className="st-player__name">{attempt.quiz_title}</p>
          <div className="row" style={{ gap: 8 }}>
            <KindBadge kind={attempt.kind} />
            {attempt.attempt_no > 1 && <Badge>Attempt {attempt.attempt_no}</Badge>}
          </div>
        </div>
        <div className="st-player__status">
          <SaveStatus status={status} onRetry={retryAll} />
          <Timerbox left={left} total={totalMs} />
        </div>
        <div className="st-player__progress">
          <ProgressBar value={answeredCount} max={total} label={`${answeredCount} of ${total} answered`} />
          <span className="faint num">{answeredCount}/{total} answered</span>
        </div>
      </header>

      {timeUp && <Alert tone="warning" title="Time is up">Submitting the answers you saved…</Alert>}
      {attempt.instructions && idx === 0 && <Alert tone="info" title="Instructions">{attempt.instructions}</Alert>}

      <div className="st-player__grid">
        <section className="st-qcard card" aria-labelledby="st-qtext">
          <div className="st-qcard__meta">
            <span className="st-qcard__num">Question {idx + 1} <span className="faint">of {total}</span></span>
            <span className="row" style={{ gap: 6 }}>
              {q.topic && <Badge>{q.topic}</Badge>}
              {q.difficulty && <Badge>{DIFFICULTY_TEXT[q.difficulty] || q.difficulty}</Badge>}
              <Badge>{plural(q.marks, 'mark')}</Badge>
            </span>
          </div>
          <motion.div key={qid} initial={reduce ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: reduce ? 0 : 0.18 }}>
              <h2 id="st-qtext" className="st-qtext">{q.text}</h2>
              <div className="st-options" role="radiogroup" aria-labelledby="st-qtext">
                {q.options.map((o, i) => {
                  const st = optionState(o)
                  return (
                    <button key={o.id} type="button" role="radio" aria-checked={a.option_id === o.id}
                      className="st-option" data-state={st || undefined} disabled={locked && st !== 'correct' && st !== 'wrong' ? true : undefined}
                      aria-disabled={locked || undefined}
                      onClick={() => choose(o.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                          e.preventDefault()
                          const sib = e.currentTarget.parentElement.children[(i + (e.key === 'ArrowDown' ? 1 : -1) + q.options.length) % q.options.length]
                          sib?.focus()
                        }
                      }}>
                      <span className="st-option__key" aria-hidden="true">{o.label}</span>
                      <span className="st-option__text">{o.text}</span>
                      {st === 'correct' && <CheckCircle2 size={18} className="st-option__icon" aria-label="Correct answer" />}
                      {st === 'wrong' && <XCircle size={18} className="st-option__icon" aria-label="Your answer, incorrect" />}
                      <span className="visually-hidden">, press {i + 1} or {o.label}</span>
                    </button>
                  )
                })}
              </div>
          </motion.div>

          {attempt.confidence_enabled && (
            <div className="st-conf" role="group" aria-label="How confident are you? Optional">
              <span className="st-conf__label">How sure are you? <span className="faint">(optional)</span></span>
              <div className="st-conf__opts">
                {CONFIDENCE.map((c) => (
                  <button key={c.v} type="button" className="st-conf__btn" aria-pressed={a.confidence === c.v} disabled={locked}
                    onClick={() => setConfidence(c.v)}>{c.label}</button>
                ))}
              </div>
            </div>
          )}

          {chk && (
            <div className={`st-feedback st-feedback--${chk.is_correct ? 'ok' : 'bad'}`} role="status">
              <p className="st-feedback__head">
                {chk.is_correct ? <CheckCircle2 size={18} aria-hidden="true" /> : <XCircle size={18} aria-hidden="true" />}
                {chk.is_correct ? 'Correct' : `Not quite. The answer is ${q.options.find((o) => o.id === chk.correct_option_id)?.label || ''}.`}
              </p>
              {chk.explanation && <p className="st-feedback__text">{chk.explanation}</p>}
              <p className="faint st-small">This answer is now locked. Explanations are AI-generated; double-check anything that looks wrong.</p>
            </div>
          )}

          {actionErr && <Alert tone="error">{actionErr.message}</Alert>}

          <div className="st-qcard__tools">
            <div className="row" style={{ gap: 8 }}>
              <Button size="sm" variant={flags.includes(qid) ? 'secondary' : 'ghost'} icon={Flag} onClick={toggleFlag} aria-pressed={flags.includes(qid)}
                className={flags.includes(qid) ? 'st-flagged' : undefined}>
                {flags.includes(qid) ? 'Flagged for review' : 'Flag for review'}
              </Button>
              {a.option_id && !locked && <Button size="sm" variant="ghost" icon={Eraser} onClick={clear}>Clear answer</Button>}
            </div>
            {attempt.can_check_answers && !locked && (
              <Button size="sm" variant="teal" icon={Check} onClick={check} loading={checking === qid} disabled={!a.option_id}
                title={a.option_id ? 'Reveal the correct answer and lock this one' : 'Choose an answer first'}>
                Check answer
              </Button>
            )}
          </div>

          <nav className="st-qcard__nav" aria-label="Question navigation">
            <Button variant="secondary" icon={ChevronLeft} onClick={() => go(idx - 1)} disabled={idx === 0}>Previous</Button>
            {idx < total - 1
              ? <Button variant="secondary" iconRight={ChevronRight} onClick={() => go(idx + 1)}>Next</Button>
              : <Button variant="teal" icon={Send} onClick={() => setConfirm(true)}>Review and submit</Button>}
          </nav>
        </section>

        <aside className="st-navigator card card--flat" aria-label="Question navigator">
          <div className="row-between">
            <h2 className="st-navigator__title">Questions</h2>
            <span className="faint st-small num">{unanswered} unanswered</span>
          </div>
          <ol className="st-navgrid">
            {questions.map((x, i) => {
              const id = String(x.question_id)
              const ans = !!answers[id]?.option_id
              const c = checks[id]
              const s = saveState[id]
              const desc = [ans ? 'answered' : 'unanswered', flags.includes(id) ? 'flagged' : null, c ? (c.is_correct ? 'checked correct' : 'checked incorrect') : null,
                s === 'error' ? 'not saved' : null].filter(Boolean).join(', ')
              return (
                <li key={id}>
                  <button type="button" className="st-navbtn" aria-current={i === idx ? 'step' : undefined}
                    data-answered={ans || undefined} data-flagged={flags.includes(id) || undefined}
                    data-check={c ? (c.is_correct ? 'ok' : 'bad') : undefined} data-error={s === 'error' || undefined}
                    onClick={() => go(i)} aria-label={`Question ${i + 1}, ${desc}`}>
                    {i + 1}
                    {flags.includes(id) && <Flag size={10} className="st-navbtn__flag" aria-hidden="true" />}
                  </button>
                </li>
              )
            })}
          </ol>
          <ul className="st-navkey" aria-hidden="true">
            <li><span className="st-navkey__sw st-navkey__sw--ans" />Answered</li>
            <li><span className="st-navkey__sw" />Unanswered</li>
            <li><Flag size={11} />Flagged</li>
          </ul>
          <Button variant="teal" block icon={Send} onClick={() => setConfirm(true)}>Submit quiz</Button>
          <p className="faint st-small st-navigator__keys">Keys: <span className="kbd">1</span>–<span className="kbd">4</span> or <span className="kbd">A</span>–<span className="kbd">D</span> choose · <span className="kbd">←</span> <span className="kbd">→</span> move</p>
        </aside>
      </div>

      <ConfirmDialog open={confirm} onClose={() => !submitting && setConfirm(false)} onConfirm={doSubmit} loading={submitting}
        title="Submit your answers?" confirmLabel="Submit now" tone="teal">
        <div className="stack">
          <p>You answered <strong>{answeredCount} of {total}</strong> questions.</p>
          {unanswered > 0 && (
            <Alert tone="warning" title={`${plural(unanswered, 'question')} unanswered`}>
              Unanswered questions are counted as skipped. Questions: {questions.map((x, i) => (!answers[x.question_id]?.option_id ? i + 1 : null)).filter(Boolean).join(', ')}.
            </Alert>
          )}
          {flags.length > 0 && <p className="muted st-small"><Flag size={13} className="st-inline-icon" aria-hidden="true" /> {plural(flags.length, 'question')} flagged for review: {questions.map((x, i) => (flags.includes(String(x.question_id)) ? i + 1 : null)).filter(Boolean).join(', ')}.</p>}
          {failedCount > 0 && <Alert tone="error" title="Some answers are not saved"><AlertTriangle size={13} className="st-inline-icon" aria-hidden="true" /> They will be retried before submitting. If they still fail, only saved answers count.</Alert>}
          <p className="muted st-small">{isPractice ? 'You will see your score and every explanation next.' : 'After submitting you cannot change your answers.'}</p>
        </div>
      </ConfirmDialog>
    </div>
  )
}
