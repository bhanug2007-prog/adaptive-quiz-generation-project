import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Search, Users } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Badge, Button, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, Select } from '../../components/ui'
import { pct, plural, relative } from '../../utils/format'

const PAGE = 25

export default function Students() {
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [course, setCourse] = useState('')
  const [page, setPage] = useState(1)
  const courses = useApi(() => lecturerApi.courses(), [])
  useEffect(() => { const t = setTimeout(() => { setQ(search.trim()); setPage(1) }, 300); return () => clearTimeout(t) }, [search])
  const d = useApi(() => lecturerApi.students({ q: q || undefined, course_id: course || undefined, page, page_size: PAGE }), [q, course, page])
  const pages = d.data ? Math.max(1, Math.ceil(d.data.total / PAGE)) : 1

  return (
    <div className="lc-page">
      <PageHeader eyebrow="Students" title="Students" subtitle="Everyone enrolled in your courses. Open a student for topic mastery, the evidence behind it and their attempts." />
      <div className="lc-filters" role="search">
        <Field label="Search">
          {(a) => (
            <div className="lc-search">
              <Search size={15} aria-hidden="true" />
              <Input {...a} type="search" placeholder="Name or email" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
          )}
        </Field>
        <Field label="Course">
          {(a) => (
            <Select {...a} value={course} onChange={(e) => { setCourse(e.target.value); setPage(1) }}>
              <option value="">All courses</option>
              {(courses.data || []).map((c) => <option key={c.id} value={c.id}>{c.code} · {c.title}</option>)}
            </Select>
          )}
        </Field>
      </div>
      {d.loading && !d.data && <LoadingBlock rows={4} label="Loading students" />}
      {d.error && <ErrorState error={d.error} onRetry={d.reload} />}
      {d.data && (d.data.items.length === 0 ? (
        q || course ? <EmptyState icon={Search} title="No students match">Try another name or course.</EmptyState> : (
          <EmptyState icon={Users} title="No students yet" action={<Button to="/lecturer/courses">Go to courses</Button>}>
            Share a course join code or enrol students by email on the course page.
          </EmptyState>
        )
      ) : (
        <div className="stack">
          <p className="muted lc-small" aria-live="polite">{plural(d.data.total, 'student')}</p>
          <div className="table-wrap" aria-busy={d.loading || undefined}>
            <table className="table">
              <thead>
                <tr><th scope="col">Student</th><th scope="col">Courses</th><th scope="col" className="num">Submissions</th><th scope="col" className="num">Average</th><th scope="col">Weak topics</th><th scope="col">Last activity</th></tr>
              </thead>
              <tbody>
                {d.data.items.map((s) => (
                  <tr key={s.student_id}>
                    <td>
                      <Link className="lc-cell-link" to={`/lecturer/students/${s.student_id}`}>{s.name}</Link>
                      <span className="faint lc-small lc-block">{[s.roll_number, s.email].filter(Boolean).join(' · ')}</span>
                    </td>
                    <td className="lc-small">{s.courses.join(', ')}</td>
                    <td className="num">{s.submissions}</td>
                    <td className="num">{s.average == null ? <span className="faint">—</span> : pct(s.average)}</td>
                    <td>{s.submissions === 0 ? <Badge>No submissions yet</Badge> : s.weak_topics ? <Badge tone="error">{plural(s.weak_topics, 'topic')}</Badge> : <span className="faint lc-small">None</span>}</td>
                    <td className="lc-small muted">{s.last_activity ? relative(s.last_activity) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="faint lc-small">Average is the mean final percentage of each student's latest submitted attempt per quiz. No submissions means not enough evidence, not weak performance.</p>
          {pages > 1 && (
            <nav className="lc-pager" aria-label="Pages">
              <Button size="sm" icon={ChevronLeft} disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <span className="lc-small muted">Page {page} of {pages}</span>
              <Button size="sm" iconRight={ChevronRight} disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
            </nav>
          )}
        </div>
      ))}
    </div>
  )
}
