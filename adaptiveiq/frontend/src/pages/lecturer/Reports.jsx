import { useState } from 'react'
import { Download, FileBarChart, ShieldCheck } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Alert, Badge, Button, Card, EmptyState, ErrorState, LoadingBlock, PageHeader, useToast } from '../../components/ui'
import { CourseGate, CourseSelect, useCourses } from '../../components/lecturer/CoursePicker'
import { QUIZ_REPORTS } from '../../components/lecturer/QuizExport'
import { QUIZ_STATUS, errText, slug } from '../../components/lecturer/util'

const COURSE_REPORTS = [
  { key: 'marks', label: 'Student-wise marks', desc: 'One row per student: each quiz’s final percentage and the total contribution points earned.', fn: lecturerApi.downloadCourseMarks },
  { key: 'topics', label: 'Topic-wise performance', desc: 'One row per student and topic: mastery label, estimated score and likely range, answers, different questions and evidence level.', fn: lecturerApi.downloadCourseTopics },
]

function useDownload() {
  const { notify } = useToast()
  const [busy, setBusy] = useState(null)
  const get = async (key, fn, id, name) => {
    setBusy(key)
    try { await fn(id, name); notify('Download started') } catch (e) { notify(errText(e), 'error') } finally { setBusy(null) }
  }
  return { busy, get }
}

export default function Reports() {
  const courses = useCourses()
  const [courseId, setCourseId] = useState('')
  return (
    <div className="lc-page">
      <PageHeader eyebrow="Reports" title="Reports and export"
        subtitle="CSV files of results you are authorised to see. They open in Excel or Google Sheets." />
      <Alert tone="info" title="Personal data">
        <span className="row" style={{ gap: 6 }}><ShieldCheck size={14} aria-hidden="true" />Reports include student names, emails and roll numbers. The server checks that each course and quiz is yours before exporting. Store the files securely.</span>
      </Alert>
      <div style={{ marginTop: 'var(--space-5)' }}>
        <CourseGate courses={courses} emptyText="Create a course and publish quizzes. Reports become available once students submit.">
          {(list) => (
            <div className="stack-lg">
              <div className="lc-filters lc-filters--course"><CourseSelect courses={list} value={courseId} onChange={setCourseId} /></div>
              {courseId && <CourseReports course={list.find((c) => String(c.id) === courseId)} />}
            </div>
          )}
        </CourseGate>
      </div>
    </div>
  )
}

function CourseReports({ course }) {
  const quizzes = useApi(() => lecturerApi.quizzes({ course_id: course.id }), [course.id])
  const dl = useDownload()
  const list = (quizzes.data || []).filter((z) => z.status === 'published' || z.status === 'archived')
  return (
    <>
      <Card title="Course reports" subtitle={`${course.code} · ${course.title}`}>
        <ul className="list-plain lc-reports">
          {COURSE_REPORTS.map((r) => (
            <li key={r.key}>
              <div><strong>{r.label}</strong><p className="faint lc-small">{r.desc}</p></div>
              <Button size="sm" icon={Download} loading={dl.busy === r.key} aria-label={`Download ${r.label} CSV`}
                onClick={() => dl.get(r.key, r.fn, course.id, `${slug(course.code)}-${r.key}.csv`)}>CSV</Button>
            </li>
          ))}
        </ul>
      </Card>
      <Card title="Quiz reports" subtitle="Per quiz: results (raw score, percentage and contribution kept separate), completion, and question-level analysis.">
        {quizzes.loading && <LoadingBlock rows={2} label="Loading quizzes" />}
        {quizzes.error && <ErrorState error={quizzes.error} onRetry={quizzes.reload} />}
        {quizzes.data && (list.length === 0 ? (
          <EmptyState icon={FileBarChart} title="No published quizzes in this course" action={<Button to="/lecturer/quizzes">Go to quizzes</Button>}>Publish a quiz to get its results, completion and question reports.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th scope="col">Quiz</th>{QUIZ_REPORTS.map((r) => <th key={r.key} scope="col">{r.label}</th>)}</tr></thead>
              <tbody>
                {list.map((z) => (
                  <tr key={z.id}>
                    <td>{z.title} <Badge tone={QUIZ_STATUS[z.status]?.tone}>{QUIZ_STATUS[z.status]?.text}</Badge></td>
                    {QUIZ_REPORTS.map((r) => (
                      <td key={r.key}>
                        <Button size="sm" variant="ghost" icon={Download} loading={dl.busy === `${z.id}-${r.key}`} aria-label={`Download ${r.label} CSV for ${z.title}`}
                          onClick={() => dl.get(`${z.id}-${r.key}`, r.fn, z.id, `${slug(z.title)}-${r.key}.csv`)}>CSV</Button>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
        <ul className="list-plain lc-small faint" style={{ marginTop: 'var(--space-3)', gap: 4 }}>
          {QUIZ_REPORTS.map((r) => <li key={r.key}><strong className="muted">{r.label}:</strong> {r.desc}</li>)}
        </ul>
      </Card>
    </>
  )
}
