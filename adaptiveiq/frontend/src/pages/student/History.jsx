import { useState } from 'react'
import { Link } from 'react-router-dom'
import { History as HistoryIcon } from 'lucide-react'
import { Badge, Button, Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Segmented } from '../../components/ui'
import { useApi } from '../../api/useApi'
import { studentApi } from '../../api/endpoints'
import { dateTime, pct } from '../../utils/format'
import { KindBadge } from '../../components/student/Badges'

export default function History() {
  const [kind, setKind] = useState('all')
  const { data, error, loading, reload } = useApi(() => studentApi.history(kind === 'all' ? undefined : kind), [kind])
  return (
    <div className="st-page stack-lg">
      <PageHeader title="Quiz History" subtitle="Every attempt you have started. Practice results are kept separate from assessment grades." />
      <Segmented name="kind" label="Show" value={kind} onChange={setKind}
        options={[{ value: 'all', label: 'All' }, { value: 'assessment', label: 'Assessments' }, { value: 'practice', label: 'Practice' }]} />
      {loading && !data ? <LoadingBlock rows={4} label="Loading history" /> : error ? <ErrorState error={error} onRetry={reload} title="Could not load your history" /> : data.length ? (
        <div className="table-wrap">
          <table className="table st-history">
            <thead>
              <tr>
                <th scope="col">Quiz</th><th scope="col">Type</th><th scope="col">Submitted</th>
                <th scope="col" className="num">Score</th><th scope="col" className="num">Correct</th><th scope="col" className="num">Incorrect</th><th scope="col" className="num">Skipped</th><th scope="col"><span className="visually-hidden">Action</span></th>
              </tr>
            </thead>
            <tbody>
              {data.map((h) => {
                const done = h.status === 'submitted'
                return (
                  <tr key={h.session_id}>
                    <td>
                      <Link className="st-history__title" to={done ? `/student/attempts/${h.session_id}/result` : `/student/attempts/${h.session_id}`}>{h.quiz_title}</Link>
                      <span className="faint st-small st-history__sub">{[h.course_title, h.topics.join(', '), `attempt ${h.attempt_no}`].filter(Boolean).join(' · ')}</span>
                    </td>
                    <td><KindBadge kind={h.kind} /></td>
                    <td className="st-nowrap">{done ? dateTime(h.submitted_at) : <Badge tone="accent">In progress</Badge>}</td>
                    <td className="num">{!done ? '—' : h.feedback_available ? pct(h.percentage) : <span className="faint">Not released</span>}</td>
                    <td className="num">{h.correct ?? '—'}</td>
                    <td className="num">{h.incorrect ?? '—'}</td>
                    <td className="num">{h.unanswered ?? '—'}</td>
                    <td>
                      <Button size="sm" variant={done ? 'ghost' : 'teal'} to={done ? `/student/attempts/${h.session_id}/result` : `/student/attempts/${h.session_id}`}
                        aria-label={`${done ? 'View result' : 'Resume'}: ${h.quiz_title}`}>{done ? 'Result' : 'Resume'}</Button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <Card>
          <EmptyState icon={HistoryIcon} title={kind === 'all' ? 'No attempts yet' : `No ${kind} attempts yet`}
            action={<Button variant="primary" to="/student/practice">Try a practice quiz</Button>}>
            Your attempts and their results will be listed here.
          </EmptyState>
        </Card>
      )}
    </div>
  )
}
