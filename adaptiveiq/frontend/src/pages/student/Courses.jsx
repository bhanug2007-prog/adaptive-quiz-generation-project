import { useState } from 'react'
import { BookOpen, FlaskConical, KeyRound, User } from 'lucide-react'
import { Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, useToast } from '../../components/ui'
import { useApi } from '../../api/useApi'
import { studentApi } from '../../api/endpoints'
import { plural } from '../../utils/format'
import Expandable from '../../components/student/Expandable'
import { practiceHref } from '../../components/student/helpers'

function JoinForm({ onJoined }) {
  const [code, setCode] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const { notify } = useToast()
  const submit = async (e) => {
    e.preventDefault()
    const v = code.trim()
    if (!v) { setErr({ message: 'Enter the join code your lecturer gave you.' }); return }
    setErr(null)
    setBusy(true)
    try {
      const c = await studentApi.join(v)
      notify(`You joined ${c.title}.`)
      setCode('')
      onJoined()
    } catch (ex) {
      setErr(ex)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card title="Join a course" subtitle="Your lecturer shares a join code in class or by email.">
      <form className="st-join" onSubmit={submit} noValidate>
        <Field label="Join code" error={err && err.status !== 403 ? err.message : null}>
          {(p) => <Input {...p} value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. 7K2M9Q" autoComplete="off" spellCheck={false} maxLength={40} />}
        </Field>
        <Button type="submit" variant="teal" icon={KeyRound} loading={busy}>Join course</Button>
      </form>
      {err?.status === 403 && <div style={{ marginTop: 12 }}><Alert tone="error">{err.message}</Alert></div>}
    </Card>
  )
}

function CourseCard({ c }) {
  const topics = c.subjects?.flatMap((s) => s.units.flatMap((u) => u.topics)) || []
  return (
    <Card as="article" className="st-course">
      <div className="row-between" style={{ alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0 }}>
          {c.code && <p className="eyebrow">{c.code}</p>}
          <h2 className="st-course__title">{c.title}</h2>
          <p className="st-course__meta">
            {c.lecturer_name && <span><User size={14} aria-hidden="true" />{c.lecturer_name}</span>}
            {[c.program, c.semester ? `Semester ${c.semester}` : null, c.academic_year].filter(Boolean).map((x) => <span key={x}>{x}</span>)}
          </p>
        </div>
        <div className="row" style={{ gap: 6 }}>
          <Badge tone="teal">{plural(c.subjects?.length || 0, 'subject')}</Badge>
          <Badge>{plural(topics.length, 'topic')}</Badge>
        </div>
      </div>
      {c.subjects?.length ? (
        <div className="st-course__subjects">
          {c.subjects.map((s) => (
            <section key={s.id} className="st-subject">
              <div className="row-between">
                <h3 className="st-subject__name">{s.name}{s.code ? <span className="faint"> · {s.code}</span> : null}</h3>
                {s.quiz_weight_cap_pct != null && <span className="faint st-small">Quizzes count up to {s.quiz_weight_cap_pct}% of the grade</span>}
              </div>
              {s.grading_notes && <p className="muted st-small">{s.grading_notes}</p>}
              <Expandable label={`Show ${plural(s.units.reduce((n, u) => n + u.topics.length, 0), 'topic')}`} openLabel="Hide topics">
                <div className="stack">
                  {s.units.map((u) => (
                    <div key={u.id}>
                      <p className="st-unit">{u.name}</p>
                      {u.topics.length ? (
                        <ul className="st-topics">
                          {u.topics.map((t) => (
                            <li key={t.id}>
                              <div style={{ minWidth: 0 }}>
                                <strong>{t.name}</strong>
                                {t.description && <p className="muted st-small">{t.description}</p>}
                                {t.objectives?.length > 0 && (
                                  <ul className="st-objectives">{t.objectives.map((o) => <li key={o.id}>{o.code ? `${o.code}: ` : ''}{o.text}</li>)}</ul>
                                )}
                              </div>
                              <Button size="sm" variant="ghost" icon={FlaskConical} to={practiceHref({ subject: s.name, topic: t.name, topic_id: t.id, difficulty: 'adaptive' })}
                                aria-label={`Practise ${t.name}`}>Practise</Button>
                            </li>
                          ))}
                        </ul>
                      ) : <p className="faint st-small">No topics in this unit yet.</p>}
                    </div>
                  ))}
                  {!s.units.length && <p className="faint st-small">Your lecturer has not added units yet.</p>}
                </div>
              </Expandable>
            </section>
          ))}
        </div>
      ) : <p className="faint st-small" style={{ marginTop: 12 }}>Your lecturer has not added subjects to this course yet.</p>}
    </Card>
  )
}

export default function Courses() {
  const { data, error, loading, reload } = useApi(() => studentApi.courses(), [])
  return (
    <div className="st-page stack-lg">
      <PageHeader title="My Courses" subtitle="Courses you are enrolled in, with their subjects and topics." />
      <JoinForm onJoined={reload} />
      {loading && !data ? <LoadingBlock rows={3} label="Loading courses" /> : error ? (
        <ErrorState error={error} onRetry={reload} title="Could not load your courses" />
      ) : data.length ? (
        <div className="stack-lg">{data.map((c) => <CourseCard key={c.id} c={c} />)}</div>
      ) : (
        <Card><EmptyState icon={BookOpen} title="No courses yet">Enter the join code from your lecturer above. Assigned quizzes appear once you join.</EmptyState></Card>
      )}
    </div>
  )
}
