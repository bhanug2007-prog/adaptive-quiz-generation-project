import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Mail } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Alert, Badge, Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Stat } from '../../components/ui'
import { dateTime, pct, plural } from '../../utils/format'
import TopicMasteryRow from '../../components/lecturer/TopicMastery'

const ORDER = { weak: 0, developing: 1, insufficient_evidence: 2, ok: 3, not_attempted: 4 }

export default function StudentProfile() {
  const { studentId } = useParams()
  const d = useApi(() => lecturerApi.student(studentId), [studentId])
  if (d.loading) return <LoadingBlock rows={4} label="Loading student" />
  if (d.error) return <ErrorState error={d.error} onRetry={d.reload} />
  const p = d.data
  const submitted = p.history.filter((h) => h.status === 'submitted')
  const topics = [...p.topics].sort((a, b) => (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9))
  const avg = submitted.filter((h) => h.percentage != null)
  const mean = avg.length ? avg.reduce((s, h) => s + h.percentage, 0) / avg.length : null

  return (
    <div className="lc-page">
      <Link to="/lecturer/students" className="lc-back"><ArrowLeft size={14} aria-hidden="true" /> All students</Link>
      <PageHeader eyebrow={p.student.roll_number || 'Student'} title={p.student.name}
        subtitle={<a className="link" href={`mailto:${p.student.email}`}><Mail size={13} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-2px' }} /> {p.student.email}</a>} />

      {p.participation.submitted === 0 && (
        <Alert tone="info" title="No submissions yet">{p.participation.note} Low participation is shown here separately from low performance.</Alert>
      )}

      <div className="grid-4" style={{ marginBottom: 'var(--space-5)' }}>
        <Stat label="Quizzes submitted" value={p.participation.submitted} />
        <Stat label="Average of submitted" value={mean == null ? '—' : pct(mean)} hint={avg.length ? `Over ${plural(avg.length, 'attempt')}` : 'No scores yet'} />
        <Stat label="Topics needing work" value={p.topics.filter((t) => t.status === 'weak').length} hint="Needs improvement, on enough evidence" />
        <Stat label="Skipped questions" value={p.skipped.length} hint="Counted separately from incorrect" />
      </div>

      <div className="lc-profile">
        <div className="stack-lg">
          <Card title="Topic mastery" subtitle="Estimates from answers in your courses and the student's own practice. Fewer than 5 different questions means not enough evidence to judge.">
            {topics.length === 0 ? <p className="muted">No topics in this student's courses yet.</p> : (
              <ul className="list-plain stack">{topics.map((t) => <TopicMasteryRow key={t.topic_key} t={t} />)}</ul>
            )}
          </Card>
          <Card title="Quiz history" subtitle="Attempts on your quizzes">
            {p.history.length === 0 ? <EmptyState title="No attempts yet">This student has not started any of your quizzes.</EmptyState> : (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Quiz</th><th>Attempt</th><th>Submitted</th><th className="num">Score</th><th className="num">Correct</th><th className="num">Unanswered</th></tr></thead>
                  <tbody>
                    {p.history.map((h) => (
                      <tr key={h.session_id}>
                        <td>{h.quiz}<span className="faint lc-small lc-block">{h.course}</span></td>
                        <td>{h.attempt_no}{h.status !== 'submitted' && <Badge style={{ marginLeft: 6 }}>{h.status === 'in_progress' ? 'In progress' : h.status}</Badge>}</td>
                        <td className="lc-small">{h.submitted_at ? dateTime(h.submitted_at) : '—'}{h.is_late && <Badge tone="warning" style={{ marginLeft: 6 }}>Late</Badge>}</td>
                        <td className="num">{h.percentage == null ? '—' : pct(h.percentage)}</td>
                        <td className="num">{h.correct ?? '—'}</td>
                        <td className="num">{h.unanswered ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
        <div className="stack-lg">
          <Card title="Recommended for revision">
            {p.recommended_revision.length === 0 ? <p className="muted lc-small">No topic is weak or developing on current evidence.</p> : (
              <ul className="list-plain stack" style={{ gap: 'var(--space-3)' }}>
                {p.recommended_revision.map((t) => (
                  <li key={t.topic_key}><strong>{t.topic}</strong><p className="faint lc-small">{t.next_action_text}</p></li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Subjects">
            {p.subjects.length === 0 ? <p className="muted lc-small">No submitted quizzes yet.</p> : (
              <ul className="list-plain stack" style={{ gap: 'var(--space-2)' }}>
                {p.subjects.map((s) => <li key={s.subject} className="row-between lc-small"><span>{s.subject}</span><span className="num">{pct(s.average)} <span className="faint">({plural(s.quizzes, 'quiz', 'quizzes')})</span></span></li>)}
              </ul>
            )}
          </Card>
          <Card title="Change over time">
            {p.change_over_time ? (
              <div className="stack" style={{ gap: 'var(--space-2)' }}>
                <p className="lc-small">Earlier quizzes <b className="num">{pct(p.change_over_time.earlier_average)}</b> → later quizzes <b className="num">{pct(p.change_over_time.later_average)}</b></p>
                <p className="faint lc-small">{p.change_over_time.note}</p>
              </div>
            ) : <p className="muted lc-small">Needs at least 3 submitted quizzes to compare.</p>}
          </Card>
          <Card title="Repeated mistakes" subtitle="Questions answered wrongly at least twice">
            {p.repeated_mistakes.length === 0 ? <p className="muted lc-small">None so far.</p> : (
              <ul className="list-plain stack" style={{ gap: 'var(--space-2)' }}>
                {p.repeated_mistakes.map((m) => <li key={m.question_id} className="lc-small"><p>{m.text}</p><p className="faint">{m.topic} · wrong {m.times_wrong} times</p></li>)}
              </ul>
            )}
          </Card>
          <Card title="Skipped questions">
            {p.skipped.length === 0 ? <p className="muted lc-small">None skipped.</p> : (
              <ul className="list-plain stack" style={{ gap: 'var(--space-2)' }}>
                {p.skipped.map((s, i) => <li key={i} className="lc-small"><p>{s.text}</p><p className="faint">{s.quiz}</p></li>)}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
