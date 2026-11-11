import { Link, useSearchParams } from 'react-router-dom'
import { ListChecks, PlusCircle } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Badge, Button, EmptyState, ErrorState, Field, LoadingBlock, PageHeader, Segmented, Select } from '../../components/ui'
import { dateTime } from '../../utils/format'
import { QUIZ_STATUS } from '../../components/lecturer/util'

const FILTERS = [
  { value: '', label: 'All' }, { value: 'draft', label: 'Drafts' }, { value: 'published', label: 'Published' }, { value: 'archived', label: 'Archived' },
]

function quizMonitoringCell(z) {
  const s = z.monitoring_summary
  const enabled = s ? s.enabled : Boolean(
    z.monitor_tab || (z.monitor_fullscreen && z.monitor_fullscreen !== 'off') || z.monitor_camera || z.monitor_microphone,
  )
  const hasRecords = (s?.monitored_count || 0) > 0
  if (!enabled && !hasRecords) return <span className="faint lc-small">Off</span>
  return (
    <div className="stack" style={{ gap: 2, justifyItems: 'start' }}>
      <Link className="lc-cell-link lc-small" to={`/lecturer/quizzes/${z.id}?step=monitoring`}>
        {enabled ? 'Monitoring & activity' : 'Earlier activity'}
      </Link>
      {s ? (
        <span className={(s.awaiting_review || s.needs_review) ? 'lc-warn lc-small' : 'faint lc-small'}>
          {s.awaiting_review > 0
            ? `${s.awaiting_review} awaiting review`
            : s.monitored_count > 0
              ? `${s.monitored_count} monitored`
              : 'Enabled'}
        </span>
      ) : (
        <span className="faint lc-small">Enabled</span>
      )}
    </div>
  )
}

export default function Quizzes() {
  const [sp, setSp] = useSearchParams()
  const status = sp.get('status') || ''
  const course = sp.get('course') || ''
  const setParam = (k, v) => setSp((p) => { const n = new URLSearchParams(p); if (v) n.set(k, v); else n.delete(k); return n }, { replace: true })
  const courses = useApi(() => lecturerApi.courses(), [])
  const d = useApi(() => lecturerApi.quizzes({ status: status || undefined, course_id: course || undefined }), [status, course])

  return (
    <div className="lc-page">
      <PageHeader eyebrow="Quizzes" title="Quizzes"
        subtitle="Drafts wait for your review. Published quizzes are visible to enrolled students."
        actions={<Button variant="primary" icon={PlusCircle} to="/lecturer/create">Create quiz</Button>} />
      <div className="lc-filters lc-filters--inline">
        <div className="field">
          <span className="field__label" id="status-filter">Status</span>
          <Segmented name="status" label="Status" value={status} onChange={(v) => setParam('status', v)} options={FILTERS} />
        </div>
        <Field label="Course">
          {(a) => (
            <Select {...a} value={course} onChange={(e) => setParam('course', e.target.value)}>
              <option value="">All courses</option>
              {(courses.data || []).map((c) => <option key={c.id} value={c.id}>{c.code} · {c.title}</option>)}
            </Select>
          )}
        </Field>
      </div>
      {d.loading && !d.data && <LoadingBlock rows={4} label="Loading quizzes" />}
      {d.error && <ErrorState error={d.error} onRetry={d.reload} />}
      {d.data && (d.data.length === 0 ? (
        status || course ? (
          <EmptyState icon={ListChecks} title="No quizzes match" action={<Button onClick={() => setSp({}, { replace: true })}>Show all quizzes</Button>}>
            Nothing with this status{course ? ' in this course' : ''}.
          </EmptyState>
        ) : (
          <EmptyState icon={ListChecks} title="No quizzes yet" action={<Button variant="primary" icon={PlusCircle} to="/lecturer/create">Create your first quiz</Button>}>
            Generate questions on a topic, review them, then publish.
          </EmptyState>
        )
      ) : (
        <div className="table-wrap lc-fade" aria-busy={d.loading || undefined}>
          <table className="table lc-table">
            <thead>
              <tr>
                <th scope="col">Quiz</th><th scope="col">Status</th><th scope="col" className="num">Questions</th>
                <th scope="col">Review</th><th scope="col">Monitoring</th><th scope="col">Due</th><th scope="col" className="num">Weight</th>
              </tr>
            </thead>
            <tbody>
              {d.data.map((z) => {
                const st = QUIZ_STATUS[z.status] || { text: z.status }
                const approved = z.review_counts?.approved || 0
                return (
                  <tr key={z.id}>
                    <td>
                      <Link className="lc-cell-link" to={`/lecturer/quizzes/${z.id}`}>{z.title}</Link>
                      <span className="faint lc-small lc-block">{[z.course_title, z.topics?.join(', ')].filter(Boolean).join(' · ')}</span>
                    </td>
                    <td><Badge tone={st.tone}>{st.text}</Badge>{z.status === 'published' && z.feedback_release === 'manual' && !z.feedback_released && <span className="faint lc-small lc-block">Feedback not released</span>}</td>
                    <td className="num">{z.question_count}</td>
                    <td>{z.question_count ? (approved === z.question_count ? <span className="lc-ok lc-small">All approved</span> : <span className="lc-warn lc-small">{approved}/{z.question_count} approved</span>) : <span className="faint">—</span>}</td>
                    <td>{quizMonitoringCell(z)}</td>
                    <td className="lc-small">{z.due_at ? dateTime(z.due_at) : <span className="faint">No due date</span>}</td>
                    <td className="num">{z.graded ? `${z.contribution_pct}%` : <span className="faint">Practice</span>}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}
