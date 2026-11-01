import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Archive, ArrowLeft, BookOpen, Copy, Layers, ListPlus, Pencil, Plus, RefreshCw, Target, Trash2, UserMinus, UserPlus, Users,
} from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import {
  Alert, Badge, Button, Card, Checkbox, ConfirmDialog, Dialog, EmptyState, ErrorState, Field, Input, LoadingBlock,
  PageHeader, ProgressBar, Select, Tabs, Textarea, useToast,
} from '../../components/ui'
import { date, plural } from '../../utils/format'
import { copyText, errText, looksLikeEmail, parseEmails, pctg } from '../../components/lecturer/util'
import { CourseForm } from './Courses'

export default function CourseDetail() {
  const { courseId } = useParams()
  const d = useApi(() => lecturerApi.course(courseId), [courseId])
  const [tab, setTab] = useState('syllabus')
  const [editing, setEditing] = useState(false)
  const [confirm, setConfirm] = useState(null)
  const [busy, setBusy] = useState(false)
  const { notify } = useToast()

  if (d.loading && !d.data) return <LoadingBlock rows={4} label="Loading course" />
  if (d.error && !d.data) return <ErrorState error={d.error} onRetry={d.reload} />
  const c = d.data

  const run = async (fn, ok) => {
    setBusy(true)
    try {
      const r = await fn()
      if (r && r.id === c.id) d.setData(r)
      if (ok) notify(ok)
      setConfirm(null)
    } catch (e) {
      notify(errText(e), 'error')
    } finally {
      setBusy(false)
    }
  }
  const copy = async () => notify((await copyText(c.join_code)) ? 'Join code copied' : 'Could not copy. Select the code and copy it by hand.', 'info')

  return (
    <div className="lc-page">
      <Link to="/lecturer/courses" className="lc-back"><ArrowLeft size={14} aria-hidden="true" /> All courses</Link>
      <PageHeader eyebrow={c.code} title={c.title}
        subtitle={[c.program, c.semester && `Semester ${c.semester}`, c.academic_year, `Created ${date(c.created_at)}`].filter(Boolean).join(' · ')}
        actions={<>
          {c.archived && <Badge>Archived</Badge>}
          <Button icon={Pencil} onClick={() => setEditing(true)}>Edit course</Button>
          <Button variant="ghost" icon={Archive} onClick={() => setConfirm('archive')}>{c.archived ? 'Restore' : 'Archive'}</Button>
        </>} />

      <div className="lc-course-top">
        <Card className="lc-join" title="Join code" subtitle="Students enter this code on their Courses page.">
          <div className="row">
            <code className="lc-code lc-code--lg" aria-label={`Join code ${c.join_code}`}>{c.join_code}</code>
            <Button size="sm" icon={Copy} onClick={copy}>Copy</Button>
            <Button size="sm" variant="ghost" icon={RefreshCw} onClick={() => setConfirm('rotate')}>New code</Button>
          </div>
          <Checkbox label="Allow students to join with the code" checked={!!c.join_enabled}
            onChange={(e) => run(() => lecturerApi.updateCourse(c.id, { join_enabled: e.target.checked }), e.target.checked ? 'Joining opened' : 'Joining closed')} />
        </Card>
        <Card title="Students"><p className="lc-big num">{c.student_count ?? 0}</p><p className="faint lc-small">Active in the roster</p></Card>
        <Card title="Quizzes"><p className="lc-big num">{c.quiz_count ?? 0}</p><Link className="link lc-small" to={`/lecturer/quizzes?course=${c.id}`}>View quizzes</Link></Card>
      </div>

      <Tabs label="Course sections" value={tab} onChange={setTab}
        tabs={[{ id: 'syllabus', label: 'Subjects & topics' }, { id: 'roster', label: 'Roster' }]} />
      <div className="lc-tabpanel" role="tabpanel" key={tab}>
        {tab === 'syllabus' ? <Syllabus course={c} reload={d.reload} /> : <Roster course={c} onCount={d.reload} />}
      </div>

      <Dialog open={editing} onClose={() => setEditing(false)} title="Edit course">
        {editing && <CourseForm initial={c} submitLabel="Save" onCancel={() => setEditing(false)}
          onSubmit={async (body) => { d.setData(await lecturerApi.updateCourse(c.id, body)); setEditing(false); notify('Course saved') }} />}
      </Dialog>
      <ConfirmDialog open={confirm === 'rotate'} onClose={() => setConfirm(null)} loading={busy} confirmLabel="Make a new code"
        title="Replace the join code?" onConfirm={() => run(() => lecturerApi.rotateJoinCode(c.id), 'New join code created')}>
        <p className="muted">The current code stops working. Students already enrolled stay enrolled.</p>
      </ConfirmDialog>
      <ConfirmDialog open={confirm === 'archive'} onClose={() => setConfirm(null)} loading={busy} confirmLabel={c.archived ? 'Restore' : 'Archive'}
        title={c.archived ? 'Restore this course?' : 'Archive this course?'}
        onConfirm={() => run(() => lecturerApi.updateCourse(c.id, { archived: !c.archived }), c.archived ? 'Course restored' : 'Course archived')}>
        <p className="muted">{c.archived ? 'It will appear in your overview and analytics again.' : 'Archived courses leave your overview. Nothing is deleted, and you can restore it later.'}</p>
      </ConfirmDialog>
    </div>
  )
}

/* ---------------- Syllabus: subjects > units > topics > objectives ---------------- */

function useMutate(reload) {
  const { notify } = useToast()
  const [busy, setBusy] = useState(false)
  const run = async (fn, ok) => {
    setBusy(true)
    try {
      await fn()
      if (ok) notify(ok)
      await reload()
      return true
    } catch (e) {
      notify(errText(e), 'error')
      return false
    } finally {
      setBusy(false)
    }
  }
  return { run, busy }
}

function InlineAdd({ label, placeholder, onAdd, icon = Plus, minLength = 1 }) {
  const [v, setV] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    if (v.trim().length < minLength) return
    setBusy(true)
    const ok = await onAdd(v.trim())
    setBusy(false)
    if (ok) setV('')
  }
  return (
    <form className="lc-inline-add" onSubmit={submit}>
      <Input aria-label={label} placeholder={placeholder} value={v} onChange={(e) => setV(e.target.value)} />
      <Button type="submit" size="sm" icon={icon} loading={busy} disabled={v.trim().length < minLength}>{label}</Button>
    </form>
  )
}

function SubjectForm({ initial, onSubmit, onCancel, used }) {
  const [v, setV] = useState({
    name: initial?.name || '', code: initial?.code || '',
    cap: initial ? String(initial.quiz_weight_cap_pct) : '20', notes: initial?.grading_notes || '',
  })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const capN = Number(v.cap)
  const problem = v.name.trim().length < 2 ? 'Enter the subject name.' : !(v.cap !== '' && capN >= 0 && capN <= 100) ? 'The cap must be between 0 and 100.'
    : used != null && capN < used ? `Quizzes already use ${used}% of this subject, so the cap cannot be lower.` : null
  const submit = async (e) => {
    e.preventDefault()
    if (problem) { setError(problem); return }
    setBusy(true)
    setError(null)
    try {
      await onSubmit({ name: v.name.trim(), code: v.code.trim() || null, quiz_weight_cap_pct: capN, grading_notes: v.notes.trim() || null })
    } catch (err) {
      setError(errText(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="stack" onSubmit={submit} noValidate>
      <div className="grid-2">
        <Field label="Subject name">{(a) => <Input {...a} value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} maxLength={160} />}</Field>
        <Field label="Subject code (optional)">{(a) => <Input {...a} value={v.code} onChange={(e) => setV({ ...v, code: e.target.value })} maxLength={30} />}</Field>
      </div>
      <Field label="Quiz weight cap (% of the subject's internal assessment)"
        hint="All graded quizzes in this subject together may contribute at most this much. Publishing checks it.">
        {(a) => <Input {...a} type="number" min={0} max={100} step="0.5" value={v.cap} onChange={(e) => setV({ ...v, cap: e.target.value })} />}
      </Field>
      <Field label="Grading notes (optional)" hint="For example how the internal assessment is split in this subject.">
        {(a) => <Textarea {...a} rows={3} maxLength={2000} value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} />}
      </Field>
      {error && <Alert tone="error">{error}</Alert>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant="primary" loading={busy}>{initial ? 'Save subject' : 'Add subject'}</Button>
      </div>
    </form>
  )
}

function Syllabus({ course, reload }) {
  const [dialog, setDialog] = useState(null)   // {kind, item}
  const m = useMutate(reload)
  const allTopics = course.subjects.flatMap((s) => s.units.flatMap((u) => u.topics.map((t) => ({ ...t, path: `${s.name} › ${u.name}` }))))
  const close = () => setDialog(null)

  const del = {
    subject: (x) => m.run(() => lecturerApi.deleteSubject(x.id), 'Subject deleted'),
    unit: (x) => m.run(() => lecturerApi.deleteUnit(x.id), 'Unit deleted'),
    topic: (x) => m.run(() => lecturerApi.deleteTopic(x.id), 'Topic deleted'),
    objective: (x) => m.run(() => lecturerApi.deleteObjective(x.id), 'Objective deleted'),
  }
  const delText = {
    subject: 'Its units, topics and learning objectives are deleted too. Subjects with published quizzes cannot be deleted.',
    unit: 'Its topics and learning objectives are deleted too.',
    topic: 'Its learning objectives are deleted too. Questions keep their topic name as text.',
    objective: 'Questions tagged with it lose the tag.',
  }

  return (
    <div className="stack-lg">
      <div className="row-between">
        <p className="muted lc-small">Every quiz is tied to a subject and topic. Set the subject's quiz weight cap so publishing can check contributions.</p>
        <Button variant="primary" icon={Plus} onClick={() => setDialog({ kind: 'subject-new' })}>Add subject</Button>
      </div>
      {course.subjects.length === 0 && (
        <EmptyState icon={BookOpen} title="No subjects yet" action={<Button variant="primary" icon={Plus} onClick={() => setDialog({ kind: 'subject-new' })}>Add a subject</Button>}>
          Add a subject, then its units and topics. You need at least one topic to generate a quiz.
        </EmptyState>
      )}
      {course.subjects.map((s) => (
        <Card key={s.id} className="lc-subject" title={<span className="row" style={{ gap: 8 }}><BookOpen size={16} aria-hidden="true" style={{ color: 'var(--teal)' }} />{s.name}{s.code && <Badge>{s.code}</Badge>}</span>}
          actions={<>
            <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setDialog({ kind: 'subject-edit', item: s })}>Edit</Button>
            <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setDialog({ kind: 'delete', type: 'subject', item: s })} aria-label={`Delete subject ${s.name}`} />
          </>}>
          <div className="lc-cap">
            <div className="row-between lc-small">
              <span className="muted">Quiz weight used</span>
              <span className="num">{pctg(s.quiz_weight_used_pct)} of {pctg(s.quiz_weight_cap_pct)} cap</span>
            </div>
            <ProgressBar value={s.quiz_weight_used_pct} max={s.quiz_weight_cap_pct || 100} label="Quiz weight used" tone={s.quiz_weight_used_pct >= s.quiz_weight_cap_pct ? 'accent' : undefined} />
            {s.grading_notes && <p className="faint lc-small">{s.grading_notes}</p>}
          </div>
          <div className="stack" style={{ marginTop: 'var(--space-4)' }}>
            {s.units.length === 0 && <p className="muted lc-small">No units yet. Add the first unit below.</p>}
            {s.units.map((u) => (
              <section key={u.id} className="lc-unit" aria-label={u.name}>
                <div className="row-between">
                  <h3 className="lc-h3 row" style={{ gap: 8 }}><Layers size={15} aria-hidden="true" className="faint" />{u.name}</h3>
                  <div className="row" style={{ gap: 4 }}>
                    <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setDialog({ kind: 'unit-edit', item: u })} aria-label={`Rename unit ${u.name}`} />
                    <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setDialog({ kind: 'delete', type: 'unit', item: u })} aria-label={`Delete unit ${u.name}`} />
                  </div>
                </div>
                <ul className="list-plain lc-topics">
                  {u.topics.map((t) => {
                    const pre = allTopics.find((x) => x.id === t.prerequisite_topic_id)
                    return (
                      <li key={t.id} className="lc-topic">
                        <div className="row-between">
                          <div>
                            <strong>{t.name}</strong>
                            {pre && <span className="faint lc-small"> · needs {pre.name} first</span>}
                            {t.description && <p className="faint lc-small">{t.description}</p>}
                          </div>
                          <div className="row" style={{ gap: 4 }}>
                            <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setDialog({ kind: 'topic-edit', item: t })} aria-label={`Edit topic ${t.name}`} />
                            <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setDialog({ kind: 'delete', type: 'topic', item: t })} aria-label={`Delete topic ${t.name}`} />
                          </div>
                        </div>
                        <ul className="list-plain lc-objectives" aria-label={`Learning objectives for ${t.name}`}>
                          {t.objectives.map((o) => (
                            <li key={o.id}>
                              <Target size={13} aria-hidden="true" />
                              <span>{o.code && <span className="faint">{o.code} </span>}{o.text}</span>
                              <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setDialog({ kind: 'delete', type: 'objective', item: o })} aria-label={`Delete objective ${o.text}`} />
                            </li>
                          ))}
                        </ul>
                        <InlineAdd label="Add objective" placeholder="Learning objective, e.g. Compare FCFS and SJF" icon={ListPlus} minLength={3}
                          onAdd={(text) => m.run(() => lecturerApi.addObjective(t.id, { text }), 'Objective added')} />
                      </li>
                    )
                  })}
                </ul>
                <div><Button size="sm" icon={Plus} onClick={() => setDialog({ kind: 'topic-new', unit: u })}>Add topic</Button></div>
              </section>
            ))}
            <InlineAdd label="Add unit" placeholder="Unit name, e.g. Unit 2: Scheduling" onAdd={(name) => m.run(() => lecturerApi.addUnit(s.id, { name }), 'Unit added')} />
          </div>
        </Card>
      ))}

      <Dialog open={dialog?.kind === 'subject-new' || dialog?.kind === 'subject-edit'} onClose={close} title={dialog?.kind === 'subject-edit' ? 'Edit subject' : 'Add subject'}>
        {dialog?.kind === 'subject-new' && <SubjectForm onCancel={close} onSubmit={async (b) => { await lecturerApi.addSubject(course.id, b); await reload(); close() }} />}
        {dialog?.kind === 'subject-edit' && <SubjectForm initial={dialog.item} used={dialog.item.quiz_weight_used_pct} onCancel={close}
          onSubmit={async (b) => { await lecturerApi.updateSubject(dialog.item.id, b); await reload(); close() }} />}
      </Dialog>
      <Dialog open={dialog?.kind === 'unit-edit'} onClose={close} title="Rename unit">
        {dialog?.kind === 'unit-edit' && <UnitForm unit={dialog.item} onCancel={close} onSubmit={async (b) => { await lecturerApi.updateUnit(dialog.item.id, b); await reload(); close() }} />}
      </Dialog>
      <Dialog open={dialog?.kind === 'topic-new' || dialog?.kind === 'topic-edit'} onClose={close} title={dialog?.kind === 'topic-edit' ? 'Edit topic' : `Add topic to ${dialog?.unit?.name || ''}`}>
        {(dialog?.kind === 'topic-new' || dialog?.kind === 'topic-edit') && (
          <TopicForm topic={dialog.item} allTopics={allTopics} onCancel={close}
            onSubmit={async (b) => {
              if (dialog.kind === 'topic-edit') await lecturerApi.updateTopic(dialog.item.id, b)
              else await lecturerApi.addTopic(dialog.unit.id, b)
              await reload()
              close()
            }} />
        )}
      </Dialog>
      <ConfirmDialog open={dialog?.kind === 'delete'} onClose={close} tone="danger" confirmLabel="Delete" loading={m.busy}
        title={dialog?.kind === 'delete' ? `Delete ${dialog.type} “${dialog.item.name || dialog.item.text}”?` : ''}
        onConfirm={async () => { if (await del[dialog.type](dialog.item)) close() }}>
        {dialog?.kind === 'delete' && <p className="muted">{delText[dialog.type]} This cannot be undone.</p>}
      </ConfirmDialog>
    </div>
  )
}

function UnitForm({ unit, onSubmit, onCancel }) {
  const [name, setName] = useState(unit.name)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  return (
    <form className="stack" onSubmit={async (e) => {
      e.preventDefault()
      if (!name.trim()) return setError('Enter a name.')
      setBusy(true)
      try { await onSubmit({ name: name.trim() }) } catch (err) { setError(errText(err)) } finally { setBusy(false) }
      return undefined
    }}>
      <Field label="Unit name" error={error}>{(a) => <Input {...a} value={name} onChange={(e) => setName(e.target.value)} maxLength={160} />}</Field>
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant="primary" loading={busy}>Save</Button>
      </div>
    </form>
  )
}

function TopicForm({ topic, allTopics, onSubmit, onCancel }) {
  const [v, setV] = useState({ name: topic?.name || '', description: topic?.description || '', pre: topic?.prerequisite_topic_id ? String(topic.prerequisite_topic_id) : '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const choices = allTopics.filter((t) => !topic || t.id !== topic.id)
  const submit = async (e) => {
    e.preventDefault()
    if (!v.name.trim()) return setError('Enter the topic name.')
    setBusy(true)
    setError(null)
    try {
      await onSubmit({ name: v.name.trim(), description: v.description.trim() || null, prerequisite_topic_id: v.pre ? Number(v.pre) : null })
    } catch (err) { setError(errText(err)) } finally { setBusy(false) }
    return undefined
  }
  return (
    <form className="stack" onSubmit={submit} noValidate>
      <Field label="Topic name">{(a) => <Input {...a} value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} maxLength={160} />}</Field>
      <Field label="Description (optional)" hint="Helps the model stay on topic when it writes questions.">
        {(a) => <Textarea {...a} rows={3} maxLength={2000} value={v.description} onChange={(e) => setV({ ...v, description: e.target.value })} />}
      </Field>
      <Field label="Prerequisite topic (optional)" hint="A topic students should know first. Used when recommending revision.">
        {(a) => (
          <Select {...a} value={v.pre} onChange={(e) => setV({ ...v, pre: e.target.value })}>
            <option value="">None</option>
            {choices.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.path})</option>)}
          </Select>
        )}
      </Field>
      {error && <Alert tone="error">{error}</Alert>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant="primary" loading={busy}>{topic ? 'Save topic' : 'Add topic'}</Button>
      </div>
    </form>
  )
}

/* ---------------- Roster ---------------- */

function Roster({ course, onCount }) {
  const r = useApi(() => lecturerApi.roster(course.id), [course.id])
  const [raw, setRaw] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [remove, setRemove] = useState(null)
  const [removing, setRemoving] = useState(false)
  const [q, setQ] = useState('')
  const { notify } = useToast()

  const emails = parseEmails(raw)
  const invalid = emails.filter((e) => !looksLikeEmail(e))
  const enroll = async (e) => {
    e.preventDefault()
    setError(null)
    if (!emails.length) return setError('Paste at least one email address.')
    if (invalid.length) return setError(`These do not look like email addresses: ${invalid.join(', ')}`)
    if (emails.length > 200) return setError('Enrol at most 200 addresses at a time.')
    setBusy(true)
    try {
      const res = await lecturerApi.enroll(course.id, emails)
      setResult(res)
      if (res.enrolled.length) { setRaw(''); r.reload(); onCount() }
    } catch (err) {
      setError(errText(err))
    } finally {
      setBusy(false)
    }
    return undefined
  }
  const doRemove = async () => {
    setRemoving(true)
    try {
      await lecturerApi.removeStudent(course.id, remove.student_id)
      notify(`${remove.full_name} removed from the course`)
      setRemove(null)
      r.reload()
      onCount()
    } catch (err) {
      notify(errText(err), 'error')
    } finally {
      setRemoving(false)
    }
  }
  const list = (r.data || []).filter((s) => !q || `${s.full_name} ${s.email} ${s.roll_number || ''}`.toLowerCase().includes(q.toLowerCase()))

  return (
    <div className="lc-roster-grid">
      <Card title="Enrol by email" subtitle="Students need an AdaptiveIQ account first. Separate addresses with commas, spaces or new lines.">
        <form className="stack" onSubmit={enroll} noValidate>
          <Field label="Email addresses" hint={emails.length ? `${plural(emails.length, 'address', 'addresses')} found` : undefined}>
            {(a) => <Textarea {...a} rows={5} value={raw} onChange={(e) => setRaw(e.target.value)} placeholder="student1@college.edu, student2@college.edu" />}
          </Field>
          {error && <Alert tone="error">{error}</Alert>}
          <Button type="submit" variant="primary" icon={UserPlus} loading={busy}>Enrol students</Button>
        </form>
        {result && (
          <div className="stack lc-enroll-result" aria-live="polite">
            {result.enrolled.length > 0 && <Alert tone="success" title={`Enrolled ${result.enrolled.length}`}>{result.enrolled.join(', ')}</Alert>}
            {result.already_enrolled.length > 0 && <Alert tone="info" title={`Already enrolled ${result.already_enrolled.length}`}>{result.already_enrolled.join(', ')}</Alert>}
            {result.not_found.length > 0 && (
              <Alert tone="warning" title={`No student account for ${result.not_found.length}`}>
                {result.not_found.join(', ')}. Ask them to register as a student, or share the join code <code className="lc-code">{course.join_code}</code>.
              </Alert>
            )}
          </div>
        )}
      </Card>
      <Card title="Roster" subtitle={r.data ? plural(r.data.length, 'student') : undefined}
        actions={r.data?.length > 5 && <Input aria-label="Search the roster" type="search" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />}>
        {r.loading && <LoadingBlock rows={3} label="Loading roster" />}
        {r.error && <ErrorState error={r.error} onRetry={r.reload} />}
        {r.data && (r.data.length === 0 ? (
          <EmptyState icon={Users} title="No students yet">Share the join code <code className="lc-code">{course.join_code}</code> or enrol students by email.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Name</th><th>Email</th><th>Roll no.</th><th>Joined</th><th>Status</th><th><span className="visually-hidden">Actions</span></th></tr></thead>
              <tbody>
                {list.map((s) => (
                  <tr key={s.student_id}>
                    <td><Link className="link" to={`/lecturer/students/${s.student_id}`}>{s.full_name}</Link></td>
                    <td className="muted">{s.email}</td>
                    <td>{s.roll_number || '—'}</td>
                    <td className="muted">{date(s.enrolled_at)} <span className="faint">({s.enrolled_via === 'join_code' ? 'join code' : 'added by you'})</span></td>
                    <td>{s.status === 'active' ? <Badge tone="success">Active</Badge> : <Badge>{s.status === 'removed' ? 'Removed' : s.status}</Badge>}</td>
                    <td>{s.status === 'active' && <Button size="sm" variant="ghost" icon={UserMinus} onClick={() => setRemove(s)} aria-label={`Remove ${s.full_name}`}>Remove</Button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </Card>
      <ConfirmDialog open={!!remove} onClose={() => setRemove(null)} onConfirm={doRemove} loading={removing} tone="danger" confirmLabel="Remove"
        title={remove ? `Remove ${remove.full_name}?` : ''}>
        <p className="muted">They lose access to this course's quizzes. Their past submissions are kept. They can only rejoin if you enrol them again.</p>
      </ConfirmDialog>
    </div>
  )
}
