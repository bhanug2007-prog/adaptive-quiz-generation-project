import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AlertTriangle, CalendarDays, Check, FlaskConical, Gauge, Lightbulb, ListChecks, RefreshCw, RotateCcw, X } from 'lucide-react'
import {
  Alert, Badge, Button, Card, EmptyState, ErrorState, EvidenceMeter, LoadingBlock, MasteryChip, PageHeader, ProgressBar, Tabs, useToast,
} from '../../components/ui'
import { useApi } from '../../api/useApi'
import { studentApi } from '../../api/endpoints'
import { DIFFICULTY_TEXT, STATUS_TEXT, dateTime, plural, relative } from '../../utils/format'
import { CalibrationChart } from '../../components/student/Charts'
import { evidenceSentence, practiceHref } from '../../components/student/helpers'
import LearningPlan from '../../components/student/LearningPlan'

export function WeakAreas() {
  const { data, error, loading, reload } = useApi(() => studentApi.weakAreas(), [])
  if (loading && !data) return <LoadingBlock rows={2} />
  if (error) return <ErrorState error={error} onRetry={reload} />
  const groups = [['weak', 'Weak areas'], ['developing', 'Developing'], ['insufficient_evidence', 'Not enough evidence yet']]
  const skipped = data.often_skipped || []
  const any = groups.some(([k]) => data[k]?.length) || skipped.length > 0
  if (!any) {
    return <EmptyState icon={Check} title={data.ok?.length ? 'No weak areas right now' : 'No evidence yet'}>
      {data.ok?.length ? 'Every topic with enough answers is on track.' : 'Weak areas are found from your submitted answers. Take a quiz to begin.'}
    </EmptyState>
  }
  return (
    <div className="stack">
      {groups.map(([k, title]) => data[k]?.length ? (
        <div key={k} className="stack" style={{ gap: 8 }}>
          <p className="eyebrow">{title} ({data[k].length})</p>
          <ul className="st-weak">
            {data[k].map((t) => (
              <li key={t.topic_key}>
                <div className="st-weak__main">
                  <div className="row" style={{ gap: 8 }}>
                    <strong>{t.topic}</strong>
                    <span className="faint st-small">{t.subject}</span>
                  </div>
                  <p className="st-small">{t.status_reason}</p>
                  <p className="faint st-small row" style={{ gap: 8 }}>
                    <EvidenceMeter level={t.evidence_level} /> {t.evidence_text}: {evidenceSentence(t)}
                  </p>
                </div>
                <div className="st-weak__side">
                  <MasteryChip label={t.label} />
                  <Button size="sm" variant="teal" icon={FlaskConical} to={practiceHref({ subject: t.subject, topic: t.topic, topic_id: t.topic_id, difficulty: t.next_difficulty })}
                    aria-label={`Practise ${t.topic}`}>Practise {DIFFICULTY_TEXT[t.next_difficulty]?.toLowerCase()}</Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null)}
      {skipped.length > 0 && (
        <div className="stack" style={{ gap: 8 }}>
          <p className="eyebrow">Often left blank ({skipped.length})</p>
          <ul className="list-plain stack" style={{ gap: 6 }}>
            {skipped.map((s) => (
              <li key={s.topic_key} className="st-small"><strong>{s.topic}</strong> <span className="faint">{s.subject}</span>
                {' '}· {s.skipped} of {s.answers} questions skipped ({s.skipped_pct}%)</li>
            ))}
          </ul>
          <p className="faint st-small">{data.often_skipped_rule} Skipping is shown apart from wrong answers: it can mean running out of time, not only not knowing.</p>
        </div>
      )}
      {data.not_attempted?.length > 0 && (
        <p className="muted st-small">Not attempted yet: {data.not_attempted.map((t) => t.topic).join(', ')}.</p>
      )}
    </div>
  )
}

function Recommendations() {
  const { data, error, loading, reload, setData } = useApi(() => studentApi.recommendations(), [])
  const [refreshing, setRefreshing] = useState(false)
  const [busy, setBusy] = useState(null)
  const { notify } = useToast()
  const refresh = async () => {
    setRefreshing(true)
    try { setData(await studentApi.refreshRecommendations()); notify('Recommendations updated from your latest results.') } catch (e) { notify(e.message, 'error') } finally { setRefreshing(false) }
  }
  const act = async (id, action) => {
    setBusy(`${id}:${action}`)
    try {
      await studentApi.recommendationAction(id, action)
      setData((xs) => xs.filter((x) => x.id !== id))
      notify(action === 'done' ? 'Marked as done.' : 'Dismissed.')
    } catch (e) { notify(e.message, 'error') } finally { setBusy(null) }
  }
  return (
    <Card title="Recommendations" subtitle="What to do next, and why."
      actions={<Button size="sm" variant="ghost" icon={RefreshCw} onClick={refresh} loading={refreshing}>Refresh</Button>}>
      {loading && !data ? <LoadingBlock rows={2} /> : error ? <ErrorState error={error} onRetry={reload} /> : data.length ? (
        <ul className="st-recos st-recos--stack">
          {data.map((r) => (
            <li key={r.id} className="appear">
              <Lightbulb size={16} aria-hidden="true" />
              <div style={{ minWidth: 0 }}>
                <p>{r.reason}</p>
                <p className="faint st-small">{r.subject ? `${r.subject} · ` : ''}suggested {relative(r.created_at)}</p>
              </div>
              <div className="st-recos__acts">
                {r.kind === 'revisit_incorrect'
                  ? <Button size="sm" variant="teal" icon={RotateCcw} href="#revision">Revise</Button>
                  : <Button size="sm" variant="primary" icon={FlaskConical} to={practiceHref(r.payload)}>Practise</Button>}
                <Button size="sm" variant="ghost" icon={Check} onClick={() => act(r.id, 'done')} loading={busy === `${r.id}:done`} aria-label={`Mark done: ${r.reason}`}>Done</Button>
                <Button size="sm" variant="ghost" icon={X} onClick={() => act(r.id, 'dismiss')} loading={busy === `${r.id}:dismiss`} aria-label={`Dismiss: ${r.reason}`} />
              </div>
            </li>
          ))}
        </ul>
      ) : <EmptyState icon={Lightbulb} title="No open recommendations">Finish a quiz or press Refresh to rebuild them from your latest results.</EmptyState>}
    </Card>
  )
}

function Revision() {
  const { data, error, loading, reload } = useApi(() => studentApi.revision(), [])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const navigate = useNavigate()
  const start = async () => {
    setBusy(true)
    setErr(null)
    try {
      const r = await studentApi.startRevision()
      navigate(`/student/attempts/${r.session_id}`)
    } catch (e) { setErr(e); setBusy(false) }
  }
  return (
    <Card id="revision" className="st-anchor" title="Spaced revision" subtitle={data?.method}
      actions={data?.due?.length ? <Button variant="teal" icon={RotateCcw} onClick={start} loading={busy}>Start revision ({data.due.length > 10 ? 10 : data.due.length})</Button> : null}>
      {loading && !data ? <LoadingBlock rows={2} /> : error ? <ErrorState error={error} onRetry={reload} /> : (
        <div className="stack">
          {err && <Alert tone="error">{err.message}</Alert>}
          {data.due.length ? (
            <div className="stack" style={{ gap: 8 }}>
              <p className="eyebrow">Due now ({data.due.length})</p>
              <ul className="st-qlist">{data.due.map((x) => <li key={x.question_id}><RotateCcw size={15} aria-hidden="true" /><div><p>{x.text}</p><p className="faint st-small">{x.topic} · box {x.box} · {plural(x.reviews, 'review')}</p></div></li>)}</ul>
              {data.due.length > 10 && <p className="faint st-small">A revision quiz takes up to 10 due questions at a time.</p>}
            </div>
          ) : <p className="muted">Nothing is due right now.{data.upcoming.length ? ` The next question comes back ${relative(data.upcoming[0].due_at)}.` : ''}</p>}
          {data.upcoming.length > 0 && (
            <div className="stack" style={{ gap: 8 }}>
              <p className="eyebrow">Upcoming ({data.upcoming.length})</p>
              <ul className="st-qlist st-qlist--compact">
                {data.upcoming.slice(0, 8).map((x) => <li key={x.question_id}><CalendarDays size={15} aria-hidden="true" /><div><p>{x.text}</p><p className="faint st-small">{x.topic} · due {dateTime(x.due_at)} ({relative(x.due_at)})</p></div></li>)}
              </ul>
              {data.upcoming.length > 8 && <p className="faint st-small">And {data.upcoming.length - 8} more.</p>}
            </div>
          )}
          {!data.due.length && !data.upcoming.length && <EmptyState icon={RotateCcw} title="No revision scheduled">Questions you miss are scheduled here automatically once their results are released.</EmptyState>}
        </div>
      )}
    </Card>
  )
}

const PATTERN = {
  overconfident: { text: 'Overconfident', tone: 'warning' },
  underconfident: { text: 'Underconfident', tone: 'accent' },
  calibrated: { text: 'Well calibrated', tone: 'success' },
}

function Confidence() {
  const { data, error, loading, reload } = useApi(() => studentApi.confidence(), [])
  return (
    <Card title="Confidence calibration" subtitle="Compares how sure you said you were with whether you were right, in practice quizzes."
      actions={data?.pattern ? <Badge tone={PATTERN[data.pattern]?.tone}>{PATTERN[data.pattern]?.text}</Badge> : null}>
      {loading && !data ? <LoadingBlock rows={2} /> : error ? <ErrorState error={error} onRetry={reload} /> : (
        <div className="stack">
          {data.rated < data.min_needed ? (
            <div className="stack" style={{ gap: 8 }}>
              <p className="muted">{data.message}</p>
              <ProgressBar value={data.rated} max={data.min_needed} label="Rated answers so far" />
              <p className="faint st-small num">{data.rated} of {data.min_needed} rated answers. Rate your confidence while answering a practice quiz.</p>
            </div>
          ) : (
            <>
              <p>{data.message}</p>
              <CalibrationChart data={data} />
            </>
          )}
        </div>
      )}
    </Card>
  )
}

function StudyPlan() {
  const { data, error, loading, reload } = useApi(() => studentApi.studyPlan(), [])
  return (
    <Card title="This week's study plan" subtitle={data?.weekly_hours ? `Based on your ${data.weekly_hours} study hours a week.` : 'Built from your mastery and upcoming due dates.'}>
      {loading && !data ? <LoadingBlock rows={2} /> : error ? <ErrorState error={error} onRetry={reload} /> : (
        <div className="stack">
          {data.items.length ? (
            <ol className="st-plan">
              {data.items.map((i, n) => (
                <li key={i.topic_key}>
                  <span className="st-plan__n num" aria-hidden="true">{n + 1}</span>
                  <div className="st-plan__main">
                    <div className="row" style={{ gap: 8 }}>
                      <strong>{i.topic}</strong>
                      <Badge tone={i.status === 'weak' ? 'error' : i.status === 'developing' ? 'warning' : undefined}>{STATUS_TEXT[i.status] || i.status}</Badge>
                    </div>
                    <p className="st-small muted">{i.why}</p>
                  </div>
                  <div className="st-plan__side">
                    {i.hours != null && <span className="num st-plan__hours">{i.hours} h</span>}
                    <Button size="sm" variant="ghost" icon={FlaskConical} to={practiceHref({ subject: i.subject, topic: i.topic, topic_id: i.topic_id, difficulty: i.next_difficulty })}
                      aria-label={`Practise ${i.topic}`}>Practise</Button>
                  </div>
                </li>
              ))}
            </ol>
          ) : <EmptyState icon={CalendarDays} title="Nothing to plan yet">Your plan fills in once some topics need work or an assessment is due within a week.</EmptyState>}
          {data.note && <p className="faint st-small">{data.note} <Link to="/student/profile" className="link">Open Profile</Link></p>}
        </div>
      )}
    </Card>
  )
}

function QuestionStatus() {
  const { data, error, loading, reload } = useApi(() => studentApi.questionStatus(), [])
  const [tab, setTab] = useState('incorrect')
  return (
    <Card title="Question status" subtitle="Skipped, wrong and never-attempted questions are kept apart because they mean different things.">
      {loading && !data ? <LoadingBlock rows={2} /> : error ? <ErrorState error={error} onRetry={reload} /> : (
        <div className="stack">
          <Tabs label="Question status" value={tab} onChange={setTab} tabs={[
            { id: 'incorrect', label: `Answered incorrectly (${data.incorrect.length})` },
            { id: 'skipped', label: `Skipped in a quiz (${data.skipped.length})` },
            { id: 'never', label: `Never attempted (${data.never_attempted.reduce((n, x) => n + x.questions, 0)})` },
          ]} />
          {tab !== 'never' ? (
            data[tab].length ? (
              <ul className="st-qlist">
                {data[tab].map((x) => (
                  <li key={`${x.session_id}-${x.question_id}`}>
                    {tab === 'incorrect' ? <AlertTriangle size={15} aria-hidden="true" /> : <ListChecks size={15} aria-hidden="true" />}
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <p>{x.text}</p>
                      <p className="faint st-small">{x.topic} · <Link className="link" to={`/student/attempts/${x.session_id}/result`}>{x.quiz_title}</Link> · {relative(x.at)}</p>
                    </div>
                  </li>
                ))}
              </ul>
            ) : <p className="muted st-small">{tab === 'incorrect' ? 'No wrong answers in released results.' : 'You have not skipped any question.'}</p>
          ) : data.never_attempted.length ? (
            <ul className="st-qlist">
              {data.never_attempted.map((x) => (
                <li key={x.quiz_id}><Gauge size={15} aria-hidden="true" /><div><p><Link className="link" to={`/student/quizzes/${x.quiz_id}`}>{x.quiz_title}</Link></p><p className="faint st-small">{plural(x.questions, 'question')} you have not seen yet</p></div></li>
              ))}
            </ul>
          ) : <p className="muted st-small">You have seen every question in your assigned quizzes.</p>}
        </div>
      )}
    </Card>
  )
}

export default function Insights() {
  const { hash } = useLocation()
  useEffect(() => {
    if (!hash) return undefined
    const t = setTimeout(() => document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' }), 300)
    return () => clearTimeout(t)
  }, [hash])
  return (
    <div className="st-page stack-lg">
      <PageHeader title="Learning Insights" subtitle="Weak areas, what to do next and when to revise. Every suggestion explains its reason." />
      <LearningPlan />
      <div className="st-cols">
        <div className="stack-lg">
          <Card title="Weak areas" subtitle="Topics with consistently low results, judged on accuracy, difficulty, number of questions and how recent they are.">
            <WeakAreas />
          </Card>
          <Revision />
          <QuestionStatus />
        </div>
        <div className="stack-lg">
          <Recommendations />
          <StudyPlan />
          <Confidence />
        </div>
      </div>
    </div>
  )
}
