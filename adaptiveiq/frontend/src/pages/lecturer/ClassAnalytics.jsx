import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, Lightbulb, RotateCcw, Target } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, Select, Stat, Tabs, useToast } from '../../components/ui'
import { DIFFICULTY_TEXT, date, fromLocalInput, pct, pct01, plural } from '../../utils/format'
import { CourseGate, CourseSelect, useCourses } from '../../components/lecturer/CoursePicker'
import { ChartFigure, MasteryStacks, SimpleBars, TrendLine } from '../../components/lecturer/charts'
import Heatmap from '../../components/lecturer/Heatmap'
import { errText, slug } from '../../components/lecturer/util'

const TABS = [{ id: 'performance', label: 'Class performance' }, { id: 'heatmap', label: 'Mastery heatmap' }, { id: 'insights', label: 'Insights & coverage' }]
const EMPTY_F = { subject_id: '', unit_id: '', topic_id: '', quiz_id: '', student_id: '', from: '', to: '' }

export default function ClassAnalytics() {
  const courses = useCourses()
  const [courseId, setCourseId] = useState('')
  const [tab, setTab] = useState('performance')
  return (
    <div className="lc-page">
      <PageHeader eyebrow="Class analytics" title="Class analytics"
        subtitle="How the class is doing, where the gaps are, and what the evidence supports. Every number comes from submitted attempts." />
      <CourseGate courses={courses}>
        {(list) => (
          <>
            <div className="lc-filters lc-filters--course">
              <CourseSelect courses={list} value={courseId} onChange={setCourseId} />
            </div>
            {courseId && (
              <>
                <Tabs label="Analytics sections" value={tab} onChange={setTab} tabs={TABS} />
                <div className="lc-tabpanel" role="tabpanel" key={`${tab}-${courseId}`}>
                  {tab === 'performance' && <Performance courseId={courseId} />}
                  {tab === 'heatmap' && <HeatmapTab courseId={courseId} />}
                  {tab === 'insights' && <InsightsTab courseId={courseId} />}
                </div>
              </>
            )}
          </>
        )}
      </CourseGate>
    </div>
  )
}

function Performance({ courseId }) {
  const course = useApi(() => lecturerApi.course(courseId), [courseId])
  const quizzes = useApi(() => lecturerApi.quizzes({ course_id: courseId }), [courseId])
  const roster = useApi(() => lecturerApi.roster(courseId), [courseId])
  const [f, setF] = useState(EMPTY_F)
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value, ...(k === 'subject_id' ? { unit_id: '', topic_id: '' } : k === 'unit_id' ? { topic_id: '' } : {}) }))
  const params = {
    subject_id: f.subject_id || undefined, unit_id: f.unit_id || undefined, topic_id: f.topic_id || undefined,
    quiz_id: f.quiz_id || undefined, student_id: f.student_id || undefined,
    date_from: f.from ? fromLocalInput(`${f.from}T00:00`) : undefined, date_to: f.to ? fromLocalInput(`${f.to}T23:59`) : undefined,
  }
  const d = useApi(() => lecturerApi.courseAnalytics(courseId, params), [courseId, JSON.stringify(params)])
  const subjects = course.data?.subjects || []
  const units = (subjects.find((s) => String(s.id) === f.subject_id)?.units) || subjects.flatMap((s) => s.units)
  const topics = (units.find((u) => String(u.id) === f.unit_id)?.topics) || units.flatMap((u) => u.topics)
  const active = Object.values(f).some(Boolean)

  return (
    <div className="stack-lg">
      <div className="lc-filters" aria-label="Filters">
        <Field label="Subject">{(a) => <Select {...a} value={f.subject_id} onChange={set('subject_id')}><option value="">All</option>{subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>}</Field>
        <Field label="Unit">{(a) => <Select {...a} value={f.unit_id} onChange={set('unit_id')}><option value="">All</option>{units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</Select>}</Field>
        <Field label="Topic">{(a) => <Select {...a} value={f.topic_id} onChange={set('topic_id')}><option value="">All</option>{topics.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</Select>}</Field>
        <Field label="Quiz">{(a) => <Select {...a} value={f.quiz_id} onChange={set('quiz_id')}><option value="">All</option>{(quizzes.data || []).filter((z) => z.status !== 'draft').map((z) => <option key={z.id} value={z.id}>{z.title}</option>)}</Select>}</Field>
        <Field label="Student">{(a) => <Select {...a} value={f.student_id} onChange={set('student_id')}><option value="">All</option>{(roster.data || []).filter((s) => s.status === 'active').map((s) => <option key={s.student_id} value={s.student_id}>{s.full_name}</option>)}</Select>}</Field>
        <Field label="From">{(a) => <Input {...a} type="date" value={f.from} onChange={set('from')} />}</Field>
        <Field label="To">{(a) => <Input {...a} type="date" value={f.to} onChange={set('to')} />}</Field>
        {active && <div className="lc-filters__reset"><Button size="sm" variant="ghost" icon={RotateCcw} onClick={() => setF(EMPTY_F)}>Clear filters</Button></div>}
      </div>
      {d.loading && !d.data && <LoadingBlock rows={4} label="Loading class performance" />}
      {d.error && <ErrorState error={d.error} onRetry={d.reload} />}
      {d.data && <PerformanceBody a={d.data} loading={d.loading} />}
    </div>
  )
}

function PerformanceBody({ a, loading }) {
  if (a.students === 0) {
    return <EmptyState title="No students enrolled">Share the course join code. Class performance appears once students submit quizzes.</EmptyState>
  }
  const noSubs = a.submissions === 0
  const dist = a.distribution.map((b) => ({ name: b.range, value: b.count }))
  const trend = a.trend.map((t) => ({ name: t.title.length > 18 ? `${t.title.slice(0, 17)}…` : t.title, full: t.title, value: t.average, n: t.submissions, date: t.date }))
  const diff = a.by_difficulty.map((x) => ({ name: DIFFICULTY_TEXT[x.difficulty], value: x.accuracy == null ? null : Math.round(x.accuracy * 100), answered: x.answered, has: x.accuracy != null }))
  return (
    <div className="stack-lg lc-fade" aria-busy={loading || undefined}>
      <div className="grid-3 lc-stats">
        <Stat label="Class average" value={a.average == null ? '—' : pct(a.average)} hint={a.median == null ? 'No submissions' : `Median ${pct(a.median)}`} />
        <Stat label="Completion" value={a.completion_rate == null ? '—' : pct01(a.completion_rate)} hint={`${plural(a.submissions, 'submission')} of ${a.expected_submissions} expected`} />
        <Stat label="Skipped answers" value={a.skipped_rate == null ? '—' : pct01(a.skipped_rate)} hint="Share of answers left blank" />
      </div>
      <p className="faint lc-small">{a.note} {plural(a.students, 'student')}, {plural(a.quizzes, 'quiz', 'quizzes')} in this view.</p>
      {noSubs ? (
        <EmptyState title="No submissions in this view">Once students submit quizzes (or with wider filters), scores, trends and commonly missed questions appear here.</EmptyState>
      ) : (
        <>
          <div className="grid-2">
            <Card><ChartFigure title="Score distribution" summary={`Final percentages of ${plural(a.submissions, 'submission')}.`}
              table={{ head: ['Score range (%)', 'Submissions'], rows: dist.map((x) => [x.name, x.value]) }}>
              <SimpleBars data={dist} xLabel="Score band, lower bound (%)" yLabel="Submissions" tooltipName="Submissions" xTickFormat={(v) => String(v).split('-')[0]} />
            </ChartFigure></Card>
            <Card><ChartFigure title="Accuracy by question difficulty" summary="Share of answered (not skipped) questions that were correct."
              table={{ head: ['Difficulty', 'Answered', 'Accuracy'], rows: diff.map((x) => [x.name, x.answered, x.has ? `${x.value}%` : 'No answers']) }}>
              <SimpleBars data={diff} yMax={100} yLabel="Correct (%)" valueFormat={(v) => `${v}%`} tooltipName="Accuracy" color="var(--teal)" />
            </ChartFigure></Card>
          </div>
          <Card>
            <ChartFigure title="Score trend across assessments" height={220}
              summary={a.trend_enough ? 'Class average per quiz, in order. Different quizzes cover different content, so this is a comparison, not proof of change.' : 'A trend needs at least two quizzes with submissions.'}
              table={{ head: ['Quiz', 'Date', 'Submissions', 'Average'], rows: trend.map((t) => [t.full, date(t.date), t.n, t.value == null ? '—' : `${t.value}%`]) }}
              empty={a.trend_enough ? null : <p className="muted lc-small">Not enough data for a trend yet ({plural(trend.filter((t) => t.value != null).length, 'quiz', 'quizzes')} with submissions).</p>}>
              <TrendLine data={trend} />
            </ChartFigure>
          </Card>
        </>
      )}
      <Card title="Topic mastery distribution" subtitle="How many students are at each mastery level per topic. Not attempted and insufficient evidence are shown separately from weak.">
        {a.mastery_distribution.length === 0 ? <p className="muted lc-small">No topics match these filters.</p> : <MasteryStacks rows={a.mastery_distribution} />}
      </Card>
      <div className="grid-2">
        <Card title="Commonly missed questions" subtitle="Questions with at least 3 answers, most missed or skipped first">
          {a.commonly_missed.length === 0 ? <p className="muted lc-small">No question has 3 or more answers yet.</p> : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Question</th><th className="num">Incorrect</th><th className="num">Skipped</th><th className="num">Answers</th></tr></thead>
                <tbody>
                  {a.commonly_missed.map((m) => (
                    <tr key={m.question_id}><td>{m.text}<span className="faint lc-small lc-block">{m.topic}</span></td><td className="num">{pct01(m.pct_incorrect)}</td><td className="num">{pct01(m.pct_skipped)}</td><td className="num">{m.answers}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <Card title="Students who may need support" subtitle="No submissions (participation) is listed separately from low scores (performance).">
          {a.needs_support.length === 0 ? <p className="muted lc-small">Nobody is flagged on current evidence.</p> : (
            <ul className="list-plain stack" style={{ gap: 'var(--space-3)' }}>
              {a.needs_support.map((s) => (
                <li key={s.student_id} className="lc-support">
                  <div className="row-between">
                    <Link className="link" to={`/lecturer/students/${s.student_id}`}>{s.name}</Link>
                    <Badge tone={s.kind === 'performance' ? 'warning' : undefined}>{s.kind === 'performance' ? 'Performance' : 'Participation'}</Badge>
                  </div>
                  <p className="faint lc-small">{s.reason}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}

function HeatmapTab({ courseId }) {
  const course = useApi(() => lecturerApi.course(courseId), [courseId])
  const [subject, setSubject] = useState('')
  const [unit, setUnit] = useState('')
  const d = useApi(() => lecturerApi.heatmap(courseId, { subject_id: subject || undefined, unit_id: unit || undefined }), [courseId, subject, unit])
  const { notify } = useToast()
  const subjects = course.data?.subjects || []
  const units = subjects.find((s) => String(s.id) === subject)?.units || subjects.flatMap((s) => s.units)
  const download = async () => {
    try { await lecturerApi.downloadCourseTopics(courseId, `${slug(course.data?.code)}-topic-mastery.csv`); notify('Topic CSV downloaded') } catch (e) { notify(errText(e), 'error') }
  }
  return (
    <div className="stack">
      <div className="lc-filters">
        <Field label="Subject">{(a) => <Select {...a} value={subject} onChange={(e) => { setSubject(e.target.value); setUnit('') }}><option value="">All subjects</option>{subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>}</Field>
        <Field label="Unit">{(a) => <Select {...a} value={unit} onChange={(e) => setUnit(e.target.value)}><option value="">All units</option>{units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</Select>}</Field>
        <div className="lc-filters__reset"><Button size="sm" icon={Download} onClick={download}>Topic CSV</Button></div>
      </div>
      {d.loading && !d.data && <LoadingBlock rows={4} label="Loading heatmap" />}
      {d.error && <ErrorState error={d.error} onRetry={d.reload} />}
      {d.data && <Heatmap data={d.data} courseId={courseId} />}
    </div>
  )
}

const COVERAGE = { not_assessed: { text: 'Not assessed', tone: 'error' }, light: { text: 'Light (1–2)', tone: 'warning' }, covered: { text: 'Covered (3+)', tone: 'success' } }

function InsightsTab({ courseId }) {
  const ins = useApi(() => lecturerApi.insights(courseId), [courseId])
  const cov = useApi(() => lecturerApi.coverage(courseId), [courseId])
  return (
    <div className="stack-lg">
      <Card title={<span className="row" style={{ gap: 8 }}><Lightbulb size={16} aria-hidden="true" style={{ color: 'var(--warning)' }} />Teaching insights</span>}
        subtitle="Shown only when the stored data supports them, with the numbers behind each. Observations describe what happened; they do not claim a cause.">
        {ins.loading && <LoadingBlock rows={2} label="Loading insights" />}
        {ins.error && <ErrorState error={ins.error} onRetry={ins.reload} />}
        {ins.data && (ins.data.length === 0 ? (
          <p className="muted lc-small">No insight is supported by the data yet. Insights need, for example, at least 10 answers per topic or 5 students with enough evidence on a topic.</p>
        ) : (
          <ul className="list-plain stack">
            {ins.data.map((x, i) => (
              <li key={i} className="lc-insight" data-severity={x.severity}>
                <div className="row" style={{ gap: 8 }}>
                  <Badge tone={x.type === 'suggestion' ? 'accent' : undefined}>{x.type === 'suggestion' ? 'Suggestion' : 'Observation'}</Badge>
                </div>
                <p>{x.text}</p>
                {x.metric && <p className="faint lc-small">{Object.entries(x.metric).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${typeof v === 'number' && v <= 1 && !Number.isInteger(v) ? pct01(v) : v}`).join(' · ')}</p>}
              </li>
            ))}
          </ul>
        ))}
      </Card>
      <Card title={<span className="row" style={{ gap: 8 }}><Target size={16} aria-hidden="true" style={{ color: 'var(--teal)' }} />Syllabus coverage</span>}
        subtitle="How many approved questions in published quizzes assess each learning objective.">
        {cov.loading && <LoadingBlock rows={2} label="Loading coverage" />}
        {cov.error && <ErrorState error={cov.error} onRetry={cov.reload} />}
        {cov.data && (cov.data.objectives.length === 0 ? (
          <p className="muted lc-small">No learning objectives defined. Add them to topics on the course page to track coverage.</p>
        ) : (
          <div className="stack">
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>Objective</th><th>Topic</th><th className="num">Approved questions</th><th className="num">In published quizzes</th><th>Coverage</th></tr></thead>
                <tbody>
                  {cov.data.objectives.map((o) => (
                    <tr key={o.objective_id}>
                      <td>{o.code && <span className="faint">{o.code} </span>}{o.objective}</td>
                      <td className="lc-small">{o.topic}<span className="faint lc-block">{o.unit}</span></td>
                      <td className="num">{o.approved_questions}</td>
                      <td className="num">{o.in_published_quizzes}</td>
                      <td><Badge tone={COVERAGE[o.coverage]?.tone}>{COVERAGE[o.coverage]?.text || o.coverage}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {cov.data.has_untagged_questions && <Alert tone="info">Some approved questions are not tagged with an objective, so they do not count here. Tag them when editing in the question bank.</Alert>}
          </div>
        ))}
      </Card>
    </div>
  )
}
