import { ArrowRight, BookOpen, CalendarCheck, ClipboardList, Flame, FlaskConical, Lightbulb, RotateCcw, TrendingUp } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button, Card, EmptyState, ErrorState, MasteryChip, PageHeader, Skeleton, Stat } from '../../components/ui'
import { useApi } from '../../api/useApi'
import { studentApi } from '../../api/endpoints'
import { LABELS, dateTime, pct, plural, relative } from '../../utils/format'
import { KindBadge, QuizStateBadge } from '../../components/student/Badges'
import { MasteryBand } from '../../components/student/TopicMasteryCard'
import { isInsufficient, practiceHref } from '../../components/student/helpers'

const LABEL_ORDER = ['strong', 'proficient', 'developing', 'needs_improvement', 'insufficient_evidence', 'not_attempted']

export function MasteryDistribution({ counts, total }) {
  const entries = LABEL_ORDER.map((k) => [k, counts?.[k] || 0]).filter(([, n]) => n > 0)
  if (!total) return null
  return (
    <div className="st-dist">
      <div className="st-dist__bar" role="img" aria-label={entries.map(([k, n]) => `${n} ${LABELS[k].text}`).join(', ')}>
        {entries.map(([k, n]) => <span key={k} style={{ flexGrow: n, background: LABELS[k].color }} title={`${LABELS[k].text}: ${n}`} />)}
      </div>
      <ul className="st-dist__legend">
        {entries.map(([k, n]) => (
          <li key={k}><span className="dot" style={{ background: LABELS[k].color }} aria-hidden="true" />{LABELS[k].text}<strong className="num">{n}</strong></li>
        ))}
      </ul>
    </div>
  )
}

function OverviewSkeleton() {
  return (
    <div className="stack-lg" role="status" aria-live="polite">
      <span className="visually-hidden">Loading your overview…</span>
      <Skeleton height={40} width="45%" />
      <div className="grid-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} height={104} />)}</div>
      <div className="st-cols"><Skeleton height={320} /><Skeleton height={320} /></div>
    </div>
  )
}

export default function Overview() {
  const { data, error, loading, reload } = useApi(() => studentApi.overview(), [])
  if (loading && !data) return <OverviewSkeleton />
  if (error) return <ErrorState error={error} onRetry={reload} title="Could not load your overview" />
  const d = data
  const first = (d.name || '').split(' ')[0]
  const a = d.average_30d || {}
  const meta = [d.program, d.semester ? `Semester ${d.semester}` : null].filter(Boolean).join(' · ')
  return (
    <div className="st-page stack-lg">
      <PageHeader eyebrow={meta || 'Student portal'} title={`Welcome back${first ? `, ${first}` : ''}`}
        subtitle={d.courses.length ? null : 'Join a course with the code from your lecturer to see assigned quizzes.'}
        actions={<Button variant="primary" icon={FlaskConical} to="/student/practice">Generate practice</Button>} />

      {d.courses.length > 0 && (
        <div className="st-courses-strip" aria-label="Enrolled courses">
          <BookOpen size={15} aria-hidden="true" />
          {d.courses.map((c) => <Link key={c.id} to="/student/courses" className="st-chip">{c.code ? <strong>{c.code}</strong> : null}{c.title}</Link>)}
        </div>
      )}

      <div className="grid-4">
        <Stat icon={ClipboardList} tone="teal" label="Assigned and waiting" value={d.awaiting_count}
          hint={d.awaiting_count ? 'Quizzes you can attempt now' : 'Nothing waiting right now'} />
        <Stat icon={TrendingUp} tone="teal" label={`Assessment average, last ${a.period_days || 30} days`}
          value={a.assessment?.average == null ? '—' : pct(a.assessment.average, 1)}
          hint={a.assessment?.count ? `From ${plural(a.assessment.count, 'released result')}` : 'No released results yet'} />
        <Stat icon={FlaskConical} tone="accent" label={`Practice average, last ${a.period_days || 30} days`}
          value={a.practice?.average == null ? '—' : pct(a.practice.average, 1)}
          hint={a.practice?.count ? `From ${plural(a.practice.count, 'practice quiz', 'practice quizzes')}` : 'No practice yet'} />
        <Stat icon={Flame} tone="warning" label="Learning streak" value={plural(d.streak_days || 0, 'day')}
          hint={`${plural(d.active_days_30d || 0, 'active day')} in the last 30 days`} />
      </div>

      <div className="st-cols">
        <div className="stack-lg">
          <Card title="Waiting for you" subtitle="Assigned quizzes that are open now"
            actions={<Button size="sm" variant="ghost" to="/student/assigned" iconRight={ArrowRight}>All assigned</Button>}>
            {d.awaiting.length ? (
              <ul className="st-list">
                {d.awaiting.map((q) => (
                  <li key={q.quiz_id}>
                    <Link to={`/student/quizzes/${q.quiz_id}`} className="st-list__row">
                      <span className="st-list__main">
                        <strong>{q.title}</strong>
                        <span className="faint">{plural(q.question_count, 'question')} · {q.due_at ? `due ${dateTime(q.due_at)} (${relative(q.due_at)})` : 'no due date'}</span>
                      </span>
                      <QuizStateBadge state={q.state} />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState icon={CalendarCheck} title="You're all caught up">
                {d.courses.length ? 'No assigned quiz is open right now. Practice keeps your topics fresh.' : 'Join a course to receive quizzes from your lecturer.'}
              </EmptyState>
            )}
          </Card>

          <Card title="Recent attempts" actions={<Button size="sm" variant="ghost" to="/student/history" iconRight={ArrowRight}>History</Button>}>
            {d.recent_attempts.length ? (
              <ul className="st-list">
                {d.recent_attempts.map((r) => (
                  <li key={r.session_id}>
                    <Link to={`/student/attempts/${r.session_id}/result`} className="st-list__row">
                      <span className="st-list__main">
                        <strong>{r.quiz_title}</strong>
                        <span className="faint">Submitted {relative(r.submitted_at)}</span>
                      </span>
                      <span className="row" style={{ gap: 10 }}>
                        <KindBadge kind={r.kind} />
                        <span className="st-list__score num">{r.percentage == null ? 'Pending' : pct(r.percentage)}</span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState title="No attempts yet">Your submitted quizzes will be listed here.</EmptyState>
            )}
          </Card>
        </div>

        <div className="stack-lg">
          <Card variant="elevated" className="st-next">
            <p className="eyebrow"><Lightbulb size={13} aria-hidden="true" /> Recommended next</p>
            {d.recommendation ? (
              <>
                <p className="st-next__text">{d.recommendation.reason}</p>
                <div className="row">
                  {d.recommendation.kind === 'revisit_incorrect' ? (
                    <Button variant="teal" icon={RotateCcw} to="/student/insights#revision">Go to spaced revision</Button>
                  ) : (
                    <Button variant="primary" icon={FlaskConical} to={practiceHref(d.recommendation.payload)}>Practise {d.recommendation.topic}</Button>
                  )}
                  <Button variant="ghost" to="/student/insights">More insights</Button>
                </div>
              </>
            ) : (
              <p className="st-next__text muted">No recommendation yet. Finish a quiz and AdaptiveIQ will suggest what to do next, with the reason.</p>
            )}
            {d.revision_due > 0 && (
              <p className="st-next__due"><RotateCcw size={14} aria-hidden="true" /> {plural(d.revision_due, 'question')} due for spaced revision. <Link className="link" to="/student/insights#revision">Start revision</Link></p>
            )}
          </Card>

          <Card title="Topic mastery" subtitle={d.topics_tracked ? `${plural(d.topics_tracked, 'topic')} tracked` : null}
            actions={<Button size="sm" variant="ghost" to="/student/progress" iconRight={ArrowRight}>My progress</Button>}>
            {d.topics_tracked ? (
              <div className="stack">
                <MasteryDistribution counts={d.mastery_counts} total={d.topics_tracked} />
                {d.top_topics.length > 0 && (
                  <ul className="st-list">
                    {d.top_topics.map((t) => (
                      <li key={t.topic_key} className="st-mini">
                        <div className="row-between" style={{ gap: 8 }}>
                          <span className="st-list__main">
                            <strong>{t.topic}</strong>
                            <span className="faint">{t.subject} · {t.evidence_text}</span>
                          </span>
                          <span className="row" style={{ gap: 10 }}>
                            <MasteryChip label={t.label} showText={false} />
                            <span className="st-list__score num">{isInsufficient(t) ? '—' : `${t.score_100}/100`}</span>
                          </span>
                        </div>
                        <MasteryBand topic={t} />
                      </li>
                    ))}
                  </ul>
                )}
                {!d.top_topics.length && <p className="muted st-small">None of your topics has answers yet.</p>}
              </div>
            ) : (
              <EmptyState icon={TrendingUp} title="No topics yet">Join a course or generate a practice quiz to start tracking topics.</EmptyState>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
