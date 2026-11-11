import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft, CheckCircle2, Clock, FlaskConical, Hourglass, Lightbulb, MinusCircle, RotateCcw, ShieldCheck, XCircle,
} from 'lucide-react'
import { Alert, Badge, Button, Card, EmptyState, ErrorState, LoadingBlock, MasteryRing, PageHeader, Tabs } from '../../components/ui'
import { useApi } from '../../api/useApi'
import { MyMonitoringRecord } from '../../components/student/Monitoring'
import { studentApi } from '../../api/endpoints'
import { DIFFICULTY_TEXT, dateTime, duration, pct, plural } from '../../utils/format'
import { KindBadge } from '../../components/student/Badges'
import Expandable from '../../components/student/Expandable'
import TopicMasteryCard from '../../components/student/TopicMasteryCard'
import { practiceHref } from '../../components/student/helpers'
import { formatSourceRef } from '../../components/lecturer/util'

const OUTCOME = {
  correct: { text: 'Correct', tone: 'success', icon: CheckCircle2 },
  incorrect: { text: 'Incorrect', tone: 'error', icon: XCircle },
  skipped: { text: 'Skipped', tone: undefined, icon: MinusCircle },
}
const CONF = { 1: 'Guessing', 2: 'Unsure', 3: 'Sure' }
const num = (v, d = 1) => (v == null ? '—' : Number(v).toFixed(d).replace(/\.0+$/, ''))

function ScoreBlock({ r }) {
  const graded = r.contribution_pct != null
  return (
    <Card className="st-score">
      <div className="st-score__ring">
        <MasteryRing value={r.final_percentage == null ? null : r.final_percentage / 100} size={124} stroke={10} caption="final" />
      </div>
      <dl className="st-score__nums">
        <div>
          <dt>Raw score</dt>
          <dd className="num">{num(r.raw_score)} <span>/ {num(r.max_score)} marks</span></dd>
        </div>
        <div>
          <dt>Percentage</dt>
          <dd className="num">{pct(r.percentage, 1)}</dd>
        </div>
        <div>
          <dt>Final after late penalty</dt>
          <dd className="num">{pct(r.final_percentage, 1)}</dd>
          <p className="st-score__note">{r.is_late ? (r.late_penalty_pct ? `Submitted late: ${num(r.late_penalty_pct)}% penalty applied.` : 'Submitted late, no penalty applied.') : 'On time, no penalty.'}</p>
        </div>
        {graded && (
          <div>
            <dt>Contribution to the subject grade</dt>
            <dd className="num">{num(r.contribution_earned, 2)} <span>of {num(r.contribution_pct)} points</span></dd>
            <p className="st-score__note">This quiz is worth {num(r.contribution_pct)}% of the subject grade.</p>
          </div>
        )}
      </dl>
      {!graded && <p className="st-score__foot faint">{r.kind === 'practice' ? 'Practice results never count towards your grades.' : 'This quiz does not count towards your grade.'}</p>}
    </Card>
  )
}

function ReviewItem({ item }) {
  const o = OUTCOME[item.outcome] || OUTCOME.skipped
  const correct = item.options.find((x) => x.is_correct)
  const sourceRefLabel = formatSourceRef(item.source_ref)
  return (
    <li className="st-review card card--flat" data-outcome={item.outcome}>
      <div className="row-between" style={{ alignItems: 'flex-start' }}>
        <p className="st-review__num">Question {item.number}</p>
        <div className="row" style={{ gap: 6 }}>
          <Badge tone={o.tone} icon={o.icon}>{o.text}</Badge>
          {item.difficulty && <Badge>{DIFFICULTY_TEXT[item.difficulty] || item.difficulty}</Badge>}
        </div>
      </div>
      <h3 className="st-review__text">{item.text}</h3>
      <ul className="st-review__opts">
        {item.options.map((x) => (
          <li key={x.id} data-correct={x.is_correct || undefined} data-selected={x.selected || undefined}>
            <span className="st-option__key" aria-hidden="true">{x.label}</span>
            <span className="st-review__opt-text">{x.text}</span>
            <span className="st-review__tags">
              {x.is_correct && <span className="st-tag st-tag--ok"><CheckCircle2 size={13} aria-hidden="true" />Correct answer</span>}
              {x.selected && !x.is_correct && <span className="st-tag st-tag--bad"><XCircle size={13} aria-hidden="true" />Your answer</span>}
              {x.selected && x.is_correct && <span className="st-tag">Your answer</span>}
            </span>
          </li>
        ))}
      </ul>
      <p className="st-review__meta faint">
        {item.topic && <span>{item.topic}</span>}
        <span>{plural(item.marks, 'mark')}</span>
        {item.confidence && <span>You said: {CONF[item.confidence]}</span>}
        {item.time_spent_s != null && <span>{duration(item.time_spent_s)} on this question</span>}
        {item.outcome === 'skipped' && correct && <span>Correct answer: {correct.label}</span>}
      </p>
      {(item.explanation || item.source_excerpt || sourceRefLabel) && (
        <Expandable label="Show explanation" openLabel="Hide explanation" defaultOpen={item.outcome === 'incorrect'}>
          <div className="stack" style={{ gap: 10 }}>
            {item.explanation && <p className="st-review__expl">{item.explanation}</p>}
            {item.math_verified && <Badge tone="success" icon={ShieldCheck}>Answer verified by a Python calculation</Badge>}
            {(item.source_excerpt || sourceRefLabel) && (
              <blockquote className="st-source">
                <p className="eyebrow">{sourceRefLabel ? `From uploaded document · ${sourceRefLabel}` : 'From the reference material'}</p>
                {item.source_excerpt && <p>{item.source_excerpt}</p>}
              </blockquote>
            )}
          </div>
        </Expandable>
      )}
    </li>
  )
}

function Withheld({ r }) {
  const card = useApi(() => studentApi.quiz(r.quiz_id), [r.quiz_id])
  const due = card.data?.due_at
  return (
    <Card>
      <EmptyState icon={Hourglass} title="Your answers are submitted"
        action={<div className="row" style={{ justifyContent: 'center' }}><Button to="/student/assigned">Assigned quizzes</Button><Button variant="ghost" to="/student/history">Quiz history</Button></div>}>
        {r.feedback_message || 'Results will be released later.'}
        {due && /due date/.test(r.feedback_message || '') ? ` The due date is ${dateTime(due)}.` : ''}
        {' '}Your score, the correct answers and explanations appear here once they are released.
      </EmptyState>
    </Card>
  )
}

export default function Result() {
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const { data: r, error, loading, reload } = useApi(() => studentApi.result(sessionId), [sessionId])
  const mastery = useApi(() => studentApi.mastery(), [sessionId])
  const monitored = useApi(() => studentApi.myMonitoring(sessionId).catch((e) => (e.status === 404 ? null : Promise.reject(e))), [sessionId])
  const [filter, setFilter] = useState('all')
  const [retrying, setRetrying] = useState(false)
  const [retryErr, setRetryErr] = useState(null)

  const items = useMemo(() => (r?.items || []).filter((x) => filter === 'all' || (filter === 'mistakes' ? x.outcome !== 'correct' : x.outcome === filter)), [r, filter])

  if (loading && !r) return <LoadingBlock rows={4} label="Loading your result" />
  if (error) {
    if (error.status === 409) {
      return <ErrorState error={error} title="Not submitted yet" onRetry={() => navigate(`/student/attempts/${sessionId}`)} />
    }
    return <ErrorState error={error} onRetry={reload} title="Could not load this result" />
  }

  const retry = async () => {
    setRetrying(true)
    setRetryErr(null)
    try {
      const s = await studentApi.start(r.quiz_id)
      navigate(`/student/attempts/${s.session_id}`)
    } catch (e) {
      if (e.status === 428) { navigate(`/student/quizzes/${r.quiz_id}`); return }   // monitored: agree on the quiz page first
      setRetryErr(e)
      setRetrying(false)
    }
  }
  const byKey = Object.fromEntries((mastery.data?.topics || []).map((t) => [t.topic_key, t]))
  const mistakes = (r.items || []).filter((x) => x.outcome !== 'correct').length
  const firstReco = r.recommendations?.[0]

  return (
    <div className="st-page stack-lg">
      <Link to="/student/history" className="st-back"><ArrowLeft size={15} aria-hidden="true" />Quiz history</Link>
      <PageHeader eyebrow={`Result · attempt ${r.attempt_no}`} title={r.quiz_title}
        subtitle={<>Submitted {dateTime(r.submitted_at)}{r.submitted_by === 'time_limit' ? ' automatically when the time ran out' : ''}.</>}
        actions={<KindBadge kind={r.kind} long />} />

      {!r.feedback_available ? <Withheld r={r} /> : (
        <>
          <div className="st-result-top">
            <ScoreBlock r={r} />
            <div className="st-counts">
              <div className="st-count st-count--ok"><CheckCircle2 size={18} aria-hidden="true" /><span className="num">{r.correct}</span><span>Correct</span></div>
              <div className="st-count st-count--bad"><XCircle size={18} aria-hidden="true" /><span className="num">{r.incorrect}</span><span>Incorrect</span></div>
              <div className="st-count"><MinusCircle size={18} aria-hidden="true" /><span className="num">{r.unanswered}</span><span>Skipped</span></div>
              <div className="st-count"><Clock size={18} aria-hidden="true" />
                <span className="num">{r.active_time_s ? duration(r.active_time_s) : '—'}</span>
                <span>{r.active_time_s ? 'Time on questions' : 'Time not measured'}</span>
              </div>
            </div>
          </div>

          <div className="row">
            {r.can_retry && <Button variant="teal" icon={RotateCcw} onClick={retry} loading={retrying}>{r.kind === 'practice' ? 'Retry this quiz' : 'Start another attempt'}</Button>}
            {mistakes > 0 && <Button variant="secondary" icon={XCircle} onClick={() => { setFilter('mistakes'); document.getElementById('st-review')?.scrollIntoView({ block: 'start' }) }}>Review mistakes ({mistakes})</Button>}
            <Button variant="primary" icon={FlaskConical} to={firstReco ? practiceHref(firstReco.payload) : '/student/practice'}>Create another quiz</Button>
          </div>
          {retryErr && <Alert tone="error">{retryErr.message}</Alert>}

          {r.topics?.length > 0 && (
            <section className="stack" aria-labelledby="st-topics-h">
              <h2 id="st-topics-h" className="st-h2">Topic results</h2>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th scope="col">Topic</th><th scope="col" className="num">Correct</th><th scope="col" className="num">Incorrect</th><th scope="col" className="num">Skipped</th><th scope="col" className="num">Accuracy on answered</th></tr></thead>
                  <tbody>
                    {r.topics.map((t) => (
                      <tr key={t.topic_key}>
                        <td>{t.topic}</td><td className="num">{t.correct}</td><td className="num">{t.incorrect}</td><td className="num">{t.skipped}</td>
                        <td className="num">{t.accuracy == null ? '—' : pct(t.accuracy * 100)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted st-small">Your mastery estimate now, including this quiz:</p>
              <div className="st-topic-grid">
                {r.topics.map((t) => byKey[t.topic_key]
                  ? <TopicMasteryCard key={t.topic_key} topic={byKey[t.topic_key]} />
                  : mastery.loading ? <LoadingBlock key={t.topic_key} rows={1} /> : null)}
              </div>
            </section>
          )}

          {r.recommendations?.length > 0 && (
            <Card title="Recommended next steps" subtitle="Each one says why it was suggested.">
              <ul className="st-recos">
                {r.recommendations.map((x) => (
                  <li key={x.id}>
                    <Lightbulb size={16} aria-hidden="true" />
                    <p>{x.reason}</p>
                    {x.kind === 'revisit_incorrect'
                      ? <Button size="sm" variant="teal" to="/student/insights#revision">Spaced revision</Button>
                      : <Button size="sm" variant="primary" icon={FlaskConical} to={practiceHref(x.payload)}>Practise</Button>}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <section className="stack" id="st-review" aria-labelledby="st-review-h">
            <div className="row-between">
              <h2 id="st-review-h" className="st-h2">Question review</h2>
            </div>
            <Tabs label="Filter questions" value={filter} onChange={setFilter} tabs={[
              { id: 'all', label: `All (${r.items.length})` },
              { id: 'mistakes', label: `Mistakes (${mistakes})` },
              { id: 'incorrect', label: `Incorrect (${r.incorrect})` },
              { id: 'skipped', label: `Skipped (${r.unanswered})` },
              { id: 'correct', label: `Correct (${r.correct})` },
            ]} />
            {items.length ? <ol className="st-reviews">{items.map((it) => <ReviewItem key={it.question_id} item={it} />)}</ol>
              : <Card variant="flat"><EmptyState title="Nothing here">No questions in this group.</EmptyState></Card>}
            {r.kind === 'practice' && <p className="faint st-small">These questions and explanations were generated by AI and were not reviewed by a lecturer.</p>}
          </section>
        </>
      )}
      {monitored.data && <MyMonitoringRecord record={monitored.data} />}
    </div>
  )
}
