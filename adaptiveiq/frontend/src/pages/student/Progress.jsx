import { useMemo, useState } from 'react'
import { Repeat, RotateCcw, TrendingUp } from 'lucide-react'
import { Button, Card, EmptyState, ErrorState, Field, LoadingBlock, PageHeader, Select, Skeleton, Stat } from '../../components/ui'
import { useApi } from '../../api/useApi'
import { studentApi } from '../../api/endpoints'
import { DIFFICULTY_TEXT, LABELS, dateTime, pct01, plural } from '../../utils/format'
import TopicMasteryCard from '../../components/student/TopicMasteryCard'
import Expandable from '../../components/student/Expandable'
import { MasteryHistoryChart, ScoresChart, WeeklyActivityChart } from '../../components/student/Charts'

const SORTS = {
  status: { label: 'Needs attention first', fn: null },
  score_low: { label: 'Lowest estimate first', fn: (a, b) => (a.score ?? 2) - (b.score ?? 2) },
  score_high: { label: 'Highest estimate first', fn: (a, b) => (b.score ?? -1) - (a.score ?? -1) },
  name: { label: 'Topic name', fn: (a, b) => a.topic.localeCompare(b.topic) },
}

function Method({ method }) {
  if (!method) return null
  return (
    <Card variant="flat" className="st-method">
      <Expandable label="How mastery is estimated" openLabel="Hide the method">
        <div className="stack" style={{ gap: 12 }}>
          <p className="muted">{method.summary}</p>
          <p className="muted">Older answers count less: an answer's weight halves every {method.half_life_days} days. A label needs at least {method.min_evidence} different questions.</p>
          <dl className="st-thresholds">
            {Object.entries(method.thresholds).map(([k, v]) => (
              <div key={k}><dt><span className="dot" style={{ background: LABELS[k]?.color }} aria-hidden="true" />{LABELS[k]?.text || k}</dt><dd>{v}</dd></div>
            ))}
          </dl>
          {method.limits && <p className="muted">{method.limits}</p>}
          <p className="faint st-small">An estimate is a guide based on your answers so far, not a verdict.</p>
        </div>
      </Expandable>
    </Card>
  )
}

function HistoryPanel({ topics }) {
  const withData = topics.filter((t) => t.answers > 0).sort((a, b) => b.answers - a.answers || a.topic.localeCompare(b.topic))
  const [key, setKey] = useState(withData[0]?.topic_key || '')
  const h = useApi(() => (key ? studentApi.masteryHistory(key) : Promise.resolve(null)), [key])
  const name = topics.find((t) => t.topic_key === key)?.topic
  if (!withData.length) {
    return <Card title="Mastery over time"><EmptyState icon={TrendingUp} title="No history yet">Each submitted quiz adds a point for the topics it covers.</EmptyState></Card>
  }
  return (
    <Card>
      <div className="st-chart-controls">
        <Field label="Topic">
          {(p) => (
            <Select {...p} value={key} onChange={(e) => setKey(e.target.value)}>
              {withData.map((t) => <option key={t.topic_key} value={t.topic_key}>{t.topic} ({t.subject})</option>)}
            </Select>
          )}
        </Field>
      </div>
      {h.loading && !h.data ? <Skeleton height={240} /> : h.error ? <ErrorState error={h.error} onRetry={h.reload} /> : <MasteryHistoryChart history={h.data} topicName={name} />}
      {h.data && <DifficultyHistory points={h.data.points} />}
    </Card>
  )
}

const LEVEL_NAME = (d) => (d === 'mixed' ? 'Mixed' : DIFFICULTY_TEXT[d] || d)

/** Why the practice difficulty changed after each quiz on this topic, newest first. */
export function DifficultyHistory({ points }) {
  const rows = (points || []).filter((p) => p.difficulty_reason).slice(-5).reverse()
  if (!rows.length) return null
  return (
    <div className="st-diffhist">
      <p className="eyebrow">Practice difficulty decisions</p>
      <ul className="list-plain stack" style={{ gap: 6 }}>
        {rows.map((p, i) => (
          <li key={i} className="st-small">
            <strong>{p.previous_difficulty && p.previous_difficulty !== p.next_difficulty
              ? `${LEVEL_NAME(p.previous_difficulty)} → ${LEVEL_NAME(p.next_difficulty)}` : LEVEL_NAME(p.next_difficulty)}</strong>
            <span className="faint"> · {dateTime(p.at)}</span>
            <span className="muted lc-block"> {p.difficulty_reason}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function Breakdown({ t }) {
  if (!t.by_difficulty) return null
  const any = t.by_difficulty.some((d) => d.answered || d.skipped)
  return (
    <Card title="Accuracy by difficulty and subject" subtitle={t.breakdown_note}>
      {!any ? <p className="muted st-small">No released results yet.</p> : (
        <div className="grid-2">
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Difficulty</th><th className="num">Answered</th><th className="num">Correct</th><th className="num">Skipped</th></tr></thead>
              <tbody>
                {t.by_difficulty.map((d) => (
                  <tr key={d.difficulty}><td>{DIFFICULTY_TEXT[d.difficulty] || d.difficulty}</td><td className="num">{d.answered}</td>
                    <td className="num">{d.accuracy == null ? '—' : pct01(d.accuracy)}</td><td className="num">{d.skipped}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Subject</th><th className="num">Topics</th><th className="num">Answered</th><th className="num">Correct</th><th className="num">Skipped</th></tr></thead>
              <tbody>
                {t.by_subject.map((s) => (
                  <tr key={s.subject}><td>{s.subject}</td><td className="num">{s.topics}</td><td className="num">{s.answered}</td>
                    <td className="num">{s.accuracy == null ? '—' : pct01(s.accuracy)}</td><td className="num">{s.skipped}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  )
}

function Trends() {
  const { data: t, error, loading, reload } = useApi(() => studentApi.trends(), [])
  if (loading && !t) return <LoadingBlock rows={2} label="Loading trends" />
  if (error) return <ErrorState error={error} onRetry={reload} title="Could not load trends" />
  const fv = t.first_vs_later
  return (
    <section className="stack-lg" aria-labelledby="st-trends-h">
      <h2 id="st-trends-h" className="st-h2">Performance trends</h2>
      <div className="grid-2">
        <Card><ScoresChart scores={t.scores} enough={t.scores_enough} /></Card>
        <Card><WeeklyActivityChart weeks={t.weekly_activity} /></Card>
      </div>
      <div className="grid-2">
        <Card title="First attempt vs later attempts" subtitle="Accuracy on questions the first time you saw them, compared with questions you had seen before.">
          <div className="grid-4 st-tight">
            <Stat label="First time seen" value={pct01(fv.first_attempt.accuracy)} hint={`${fv.first_attempt.correct} of ${plural(fv.first_attempt.answered, 'answer')} correct`} />
            <Stat label="Seen before" value={pct01(fv.later_attempts.accuracy)} hint={`${fv.later_attempts.correct} of ${plural(fv.later_attempts.answered, 'answer')} correct`} />
          </div>
          {!fv.enough_data && <p className="st-chart__note" style={{ marginTop: 12 }}>Not enough data to compare yet: each side needs at least 5 answers.</p>}
        </Card>
        <Card title="Spaced revision" subtitle="Questions you missed come back for review on a schedule.">
          <div className="grid-4 st-tight">
            <Stat icon={RotateCcw} tone="teal" label="Scheduled" value={t.revision.scheduled} hint={`${t.revision.due_now} due now`} />
            <Stat label="Reviewed at least once" value={t.revision.reviewed} hint={`${t.revision.retired} retired after repeated correct answers`} />
          </div>
          <div style={{ marginTop: 12 }}><Button size="sm" variant="teal" to="/student/insights#revision">Open spaced revision</Button></div>
        </Card>
      </div>
      <Breakdown t={t} />
      <Card title="Repeated mistakes" subtitle="Questions you have answered wrongly two or more times.">
        {t.repeated_mistakes.length ? (
          <ul className="st-qlist">
            {t.repeated_mistakes.map((m) => (
              <li key={m.question_id}><Repeat size={15} aria-hidden="true" /><div><p>{m.text}</p><p className="faint st-small">{m.topic} · wrong {m.times_wrong} times</p></div></li>
            ))}
          </ul>
        ) : <p className="muted st-small">No repeated mistakes. A question shows up here if you get it wrong more than once.</p>}
      </Card>
    </section>
  )
}

export default function Progress() {
  const { data, error, loading, reload } = useApi(() => studentApi.mastery(), [])
  const [subject, setSubject] = useState('all')
  const [sort, setSort] = useState('status')
  const topics = data?.topics || []
  const subjects = useMemo(() => [...new Set(topics.map((t) => t.subject || 'Practice topics'))], [topics])
  const shown = useMemo(() => {
    const xs = topics.filter((t) => subject === 'all' || (t.subject || 'Practice topics') === subject)
    return SORTS[sort].fn ? [...xs].sort(SORTS[sort].fn) : xs
  }, [topics, subject, sort])

  return (
    <div className="st-page stack-lg">
      <PageHeader title="My Progress" subtitle="Your estimated mastery of each topic, the evidence behind it, and how it is changing." />
      {loading && !data ? <LoadingBlock rows={4} label="Loading mastery" /> : error ? (
        <ErrorState error={error} onRetry={reload} title="Could not load your mastery map" />
      ) : (
        <>
          <Method method={data.method} />
          <section className="stack" aria-labelledby="st-map-h">
            <div className="row-between" style={{ alignItems: 'flex-end' }}>
              <h2 id="st-map-h" className="st-h2">Topic mastery map <span className="faint st-small">{plural(topics.length, 'topic')}</span></h2>
              {topics.length > 1 && (
                <div className="row st-filters">
                  <Field label="Subject">
                    {(p) => (
                      <Select {...p} value={subject} onChange={(e) => setSubject(e.target.value)}>
                        <option value="all">All subjects</option>
                        {subjects.map((s) => <option key={s} value={s}>{s}</option>)}
                      </Select>
                    )}
                  </Field>
                  <Field label="Sort">
                    {(p) => (
                      <Select {...p} value={sort} onChange={(e) => setSort(e.target.value)}>
                        {Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                      </Select>
                    )}
                  </Field>
                </div>
              )}
            </div>
            {topics.length ? (
              <div className="st-topic-grid">{shown.map((t) => <TopicMasteryCard key={t.topic_key} topic={t} />)}</div>
            ) : (
              <Card><EmptyState icon={TrendingUp} title="No topics yet" action={<Button variant="primary" to="/student/practice">Generate a practice quiz</Button>}>
                Topics appear when you join a course or answer practice questions.
              </EmptyState></Card>
            )}
          </section>
          <HistoryPanel key={topics.length} topics={topics} />
        </>
      )}
      <Trends />
    </div>
  )
}
