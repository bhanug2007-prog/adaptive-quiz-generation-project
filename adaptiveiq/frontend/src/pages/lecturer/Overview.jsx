import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, BookOpen, CheckCircle2, Clock, ListChecks, PlusCircle, TrendingDown, Users } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { useAuth } from '../../auth/AuthProvider'
import { Button, Card, EmptyState, ErrorState, LoadingBlock, PageHeader, ProgressBar, Segmented, Stat } from '../../components/ui'
import { pct, pct01, plural, relative } from '../../utils/format'

const PERIODS = [{ value: '7', label: '7 days' }, { value: '30', label: '30 days' }, { value: '90', label: '90 days' }]

export default function Overview() {
  const { user } = useAuth()
  const [days, setDays] = useState('30')
  const d = useApi(() => lecturerApi.overview(Number(days)), [days])
  const first = (user?.full_name || '').split(' ')[0]

  return (
    <div className="lc-page">
      <PageHeader eyebrow="Lecturer overview" title={first ? `Welcome back, ${first}` : 'Overview'}
        subtitle="The state of your courses, from your students' submitted quizzes."
        actions={<>
          <Button to="/lecturer/courses" icon={BookOpen}>Courses</Button>
          <Button variant="primary" to="/lecturer/create" icon={PlusCircle}>Create quiz</Button>
        </>} />
      <div className="row-between" style={{ marginBottom: 'var(--space-4)' }}>
        <p className="muted lc-small">Recent average uses submissions in the selected period. Other counts are current.</p>
        <Segmented name="period" label="Time period" value={days} onChange={setDays} options={PERIODS} />
      </div>
      {d.loading && !d.data && <LoadingBlock rows={4} label="Loading overview" />}
      {d.error && <ErrorState error={d.error} onRetry={d.reload} />}
      {d.data && <Body o={d.data} />}
    </div>
  )
}

function Body({ o }) {
  const def = o.definitions || {}
  if (o.active_courses === 0) {
    return (
      <EmptyState icon={BookOpen} title="Start with a course" action={<Button variant="primary" to="/lecturer/courses">Create a course</Button>}>
        Add a course with its subjects, units and topics. Then generate a quiz, review it and publish it to your students.
      </EmptyState>
    )
  }
  return (
    <div className="stack-lg appear">
      <div className="grid-3 lc-stats">
        <Stat label="Active courses" value={o.active_courses} icon={BookOpen} tone="teal" />
        <Stat label="Published quizzes" value={o.published_quizzes} icon={ListChecks} tone="teal" />
        <Stat label="Enrolled students" value={o.enrolled_students} icon={Users} tone="teal" hint="Across active courses" />
        <Stat label="Completion rate" value={o.completion_rate == null ? '—' : pct01(o.completion_rate)} icon={CheckCircle2} tone="success"
          hint={o.expected_submissions ? `Of ${plural(o.expected_submissions, 'expected submission')} (students × opened quizzes)` : 'No opened published quizzes yet'} />
        <Stat label={`Average, last ${o.period_days} days`} value={o.recent_average == null ? '—' : pct(o.recent_average)} icon={Activity} tone="teal"
          hint={o.recent_submissions ? `From ${plural(o.recent_submissions, 'submission')}.` : 'No submissions in this period'} />
        <Stat label="Pending submissions" value={o.pending_submissions} icon={Clock} tone="warning" hint={def.pending_submissions} />
      </div>
      {o.completion_rate != null && (
        <div className="lc-inline-progress">
          <span className="lc-small muted">Completion</span>
          <ProgressBar value={o.completion_rate * 100} label="Assessment completion rate" />
          <span className="lc-small num">{pct01(o.completion_rate)}</span>
        </div>
      )}
      <div className="grid-2">
        <Card title="Largest learning gaps" subtitle={def.largest_gaps}>
          {o.largest_gaps.length === 0 ? (
            <p className="muted lc-small">No topic has enough evidence yet. A gap appears once at least 3 students have answered at least 5 different questions on a topic.</p>
          ) : (
            <ul className="list-plain lc-gaps">
              {o.largest_gaps.map((g) => (
                <li key={`${g.course_id}-${g.topic_id}`}>
                  <div className="row-between">
                    <span><TrendingDown size={14} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-2px', color: 'var(--warning)' }} /> {g.topic}</span>
                    <span className="num">{Math.round(g.mean_mastery * 100)}/100</span>
                  </div>
                  <ProgressBar value={g.mean_mastery * 100} label={`${g.topic} mean mastery`} />
                  <p className="faint lc-small">{g.course} · {plural(g.students_with_evidence, 'student')} with enough evidence</p>
                </li>
              ))}
            </ul>
          )}
          <Link to="/lecturer/analytics" className="link lc-small">Open class analytics</Link>
        </Card>
        <Card title="Recent assessment activity" subtitle="Latest submissions in your courses">
          {o.recent_activity.length === 0 ? <p className="muted lc-small">No submissions yet. Publish a quiz and share the course join code with students.</p> : (
            <ul className="list-plain lc-activity">
              {o.recent_activity.map((a, i) => (
                <li key={i}>
                  <div className="lc-activity__main">
                    <strong>{a.student}</strong>
                    <span className="muted"> submitted {a.quiz}</span>
                    <span className="faint lc-small">{a.course} · {relative(a.at)}</span>
                  </div>
                  <span className="num lc-activity__pct">{a.percentage == null ? '—' : pct(a.percentage)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
