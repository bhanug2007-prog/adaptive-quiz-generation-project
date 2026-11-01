import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { GraduationCap, Plus, Users, ListChecks } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Alert, Badge, Button, Card, Checkbox, Dialog, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, useToast } from '../../components/ui'
import { date, plural } from '../../utils/format'
import { errText } from '../../components/lecturer/util'

export function CourseForm({ initial, onSubmit, onCancel, submitLabel = 'Create course' }) {
  const [v, setV] = useState({
    code: initial?.code || '', title: initial?.title || '', program: initial?.program || '',
    semester: initial?.semester ? String(initial.semester) : '', academic_year: initial?.academic_year || '',
  })
  const [touched, setTouched] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (k) => (e) => setV((s) => ({ ...s, [k]: e.target.value }))
  const p = {}
  if (!v.code.trim()) p.code = 'Enter a course code, for example CS301.'
  if (v.title.trim().length < 2) p.title = 'Enter the course title.'
  if (v.semester && !(Number(v.semester) >= 1 && Number(v.semester) <= 12)) p.semester = 'Use a number from 1 to 12.'
  const show = touched ? p : {}
  const submit = async (e) => {
    e.preventDefault()
    setTouched(true)
    if (Object.keys(p).length) return
    setBusy(true)
    setError(null)
    try {
      await onSubmit({
        code: v.code.trim(), title: v.title.trim(), program: v.program.trim() || null,
        semester: v.semester ? Number(v.semester) : null, academic_year: v.academic_year.trim() || null,
      })
    } catch (err) {
      setError(errText(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="grid-2">
        <Field label="Course code" error={show.code}>{(a) => <Input {...a} value={v.code} onChange={set('code')} maxLength={30} placeholder="CS301" />}</Field>
        <Field label="Title" error={show.title}>{(a) => <Input {...a} value={v.title} onChange={set('title')} maxLength={200} placeholder="Operating Systems" />}</Field>
        <Field label="Programme (optional)">{(a) => <Input {...a} value={v.program} onChange={set('program')} maxLength={120} placeholder="B.Tech DSAI" />}</Field>
        <Field label="Semester (optional)" error={show.semester}>{(a) => <Input {...a} type="number" min={1} max={12} value={v.semester} onChange={set('semester')} />}</Field>
        <Field label="Academic year (optional)">{(a) => <Input {...a} value={v.academic_year} onChange={set('academic_year')} maxLength={20} placeholder="2026-27" />}</Field>
      </div>
      {error && <Alert tone="error">{error}</Alert>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        {onCancel && <Button variant="ghost" onClick={onCancel}>Cancel</Button>}
        <Button type="submit" variant="primary" loading={busy}>{submitLabel}</Button>
      </div>
    </form>
  )
}

export default function Courses() {
  const d = useApi(() => lecturerApi.courses(), [])
  const [open, setOpen] = useState(false)
  const [showArchived, setShowArchived] = useState(false)
  const navigate = useNavigate()
  const { notify } = useToast()
  const create = async (body) => {
    const c = await lecturerApi.createCourse(body)
    notify('Course created. Add a subject, units and topics next.')
    navigate(`/lecturer/courses/${c.id}`)
  }
  const list = (d.data || []).filter((c) => showArchived || !c.archived)
  const archivedCount = (d.data || []).filter((c) => c.archived).length

  return (
    <div className="lc-page">
      <PageHeader eyebrow="Courses & subjects" title="Your courses"
        subtitle="Course → subject → unit → topic. Quizzes, analytics and the question bank all hang off this structure."
        actions={<Button variant="primary" icon={Plus} onClick={() => setOpen(true)}>New course</Button>} />
      {d.loading && <LoadingBlock rows={3} label="Loading courses" />}
      {d.error && <ErrorState error={d.error} onRetry={d.reload} />}
      {d.data && (d.data.length === 0 ? (
        <EmptyState icon={GraduationCap} title="No courses yet" action={<Button variant="primary" icon={Plus} onClick={() => setOpen(true)}>Create your first course</Button>}>
          A course holds its subjects, units and topics, its roster and its quizzes. Students join with a code you share.
        </EmptyState>
      ) : (
        <div className="stack">
          {archivedCount > 0 && <Checkbox label={`Show archived (${archivedCount})`} checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />}
          <div className="grid-3">
            {list.map((c) => (
              <Card key={c.id} as="article" interactive className="lc-course-card">
                <div className="row-between">
                  <Badge tone="teal">{c.code}</Badge>
                  {c.archived && <Badge>Archived</Badge>}
                </div>
                <h2 className="lc-course-card__title"><Link to={`/lecturer/courses/${c.id}`} className="lc-stretch">{c.title}</Link></h2>
                <p className="faint lc-small">{[c.program, c.semester && `Semester ${c.semester}`, c.academic_year].filter(Boolean).join(' · ') || `Created ${date(c.created_at)}`}</p>
                <div className="row lc-small muted">
                  <span className="row" style={{ gap: 4 }}><Users size={14} aria-hidden="true" />{plural(c.student_count ?? 0, 'student')}</span>
                  <span className="row" style={{ gap: 4 }}><ListChecks size={14} aria-hidden="true" />{plural(c.quiz_count ?? 0, 'quiz', 'quizzes')}</span>
                </div>
                <div className="row lc-small">
                  <span className="faint">Join code</span>
                  <code className="lc-code">{c.join_enabled ? c.join_code : 'Joining closed'}</code>
                </div>
              </Card>
            ))}
          </div>
        </div>
      ))}
      <Dialog open={open} onClose={() => setOpen(false)} title="New course" description="You can add subjects, units and topics on the next page.">
        {open && <CourseForm onSubmit={create} onCancel={() => setOpen(false)} />}
      </Dialog>
    </div>
  )
}
