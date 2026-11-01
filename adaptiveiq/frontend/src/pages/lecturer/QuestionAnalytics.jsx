import { useState } from 'react'
import { AlertTriangle, ClipboardList, Download, Repeat } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Alert, Badge, Button, Card, Checkbox, EmptyState, ErrorState, Field, LoadingBlock, PageHeader, Select, Tabs, useToast } from '../../components/ui'
import { DIFFICULTY_TEXT, duration, pct01 } from '../../utils/format'
import { CourseGate, CourseSelect, useCourses } from '../../components/lecturer/CoursePicker'
import ModelQuality from '../../components/lecturer/ModelQuality'
import { errText, slug } from '../../components/lecturer/util'

const MIN_N = 10
const TABS = [{ id: 'questions', label: 'Question quality' }, { id: 'model', label: 'Model evaluation' }]

export default function QuestionAnalytics() {
  const [tab, setTab] = useState('questions')
  const courses = useCourses()
  return (
    <div className="lc-page">
      <PageHeader eyebrow="Question analytics" title="Question analytics"
        subtitle="How each question behaved with real students, and how the question-generation model has performed for you." />
      <Tabs label="Question analytics sections" value={tab} onChange={setTab} tabs={TABS} />
      <div className="lc-tabpanel" role="tabpanel" key={tab}>
        {tab === 'questions' ? (
          <CourseGate courses={courses} emptyText="Create a course and publish a quiz. Question statistics appear once students submit.">
            {(list) => <QuestionQuality courses={list} />}
          </CourseGate>
        ) : <ModelQuality />}
      </div>
    </div>
  )
}

function OutcomeBar({ r }) {
  if (!r.answers) return <span className="faint lc-small">No answers</span>
  const segs = [['correct', r.pct_correct, 'var(--success)'], ['incorrect', r.pct_incorrect, 'var(--error)'], ['skipped', r.pct_skipped, 'var(--m-insufficient)']]
  return (
    <div className="lc-outcome" role="img" aria-label={`${pct01(r.pct_correct)} correct, ${pct01(r.pct_incorrect)} incorrect, ${pct01(r.pct_skipped)} skipped`}>
      {segs.filter(([, v]) => v > 0).map(([k, v, c]) => <span key={k} style={{ flexGrow: v, background: c }} title={`${k} ${pct01(v)}`} />)}
    </div>
  )
}

function QuestionQuality({ courses }) {
  const [courseId, setCourseId] = useState('')
  const [quizId, setQuizId] = useState('')
  const [flagged, setFlagged] = useState(false)
  const { notify } = useToast()
  const quizzes = useApi(() => (courseId ? lecturerApi.quizzes({ course_id: courseId }) : Promise.resolve([])), [courseId])
  const d = useApi(() => {
    if (!courseId) return Promise.resolve(null)
    return quizId ? lecturerApi.quizQuestionAnalytics(quizId) : lecturerApi.courseQuestionAnalytics(courseId, flagged || undefined)
  }, [courseId, quizId, flagged])
  const rows = d.data ? (quizId && flagged ? d.data.filter((r) => r.flags.length) : d.data) : null
  const quizList = (quizzes.data || []).filter((z) => z.status !== 'draft' && z.status !== 'generating')
  const quiz = quizList.find((z) => String(z.id) === quizId)
  const download = async () => {
    try { await lecturerApi.downloadQuizQuestions(quiz.id, `${slug(quiz.title)}-questions.csv`); notify('Question CSV downloaded') } catch (e) { notify(errText(e), 'error') }
  }

  return (
    <div className="stack-lg">
      <div className="lc-filters">
        <CourseSelect courses={courses} value={courseId} onChange={(v) => { setCourseId(v); setQuizId('') }} />
        <Field label="Quiz">
          {(a) => (
            <Select {...a} value={quizId} onChange={(e) => setQuizId(e.target.value)}>
              <option value="">All quizzes in the course</option>
              {quizList.map((z) => <option key={z.id} value={z.id}>{z.title}</option>)}
            </Select>
          )}
        </Field>
        <div className="lc-filters__reset">
          <Checkbox label="Only questions with review flags" checked={flagged} onChange={(e) => setFlagged(e.target.checked)} />
          {quiz && <Button size="sm" icon={Download} onClick={download}>CSV</Button>}
        </div>
      </div>
      <Alert tone="info">
        Flags are review signals, not proof that a question is wrong: a hard question can be valid, and an ambiguous one needs a person to read it.
        Difficulty (p = share correct), discrimination and flags are only computed with at least {MIN_N} answers.
      </Alert>
      {d.loading && !d.data && <LoadingBlock rows={4} label="Loading question statistics" />}
      {d.error && <ErrorState error={d.error} onRetry={d.reload} />}
      {rows && (rows.length === 0 ? (
        <EmptyState icon={ClipboardList} title={flagged ? 'No flagged questions' : 'No question data yet'}>
          {flagged ? 'No question has a review flag on current answers.' : 'Publish a quiz in this course. Statistics appear once students submit it.'}
        </EmptyState>
      ) : (
        <Card>
          <div className="table-wrap lc-fade" aria-busy={d.loading || undefined}>
            <table className="table lc-qa">
              <caption className="visually-hidden">Per-question statistics</caption>
              <thead>
                <tr>
                  <th scope="col">Question</th><th scope="col">Difficulty</th><th scope="col" className="num">Answers</th>
                  <th scope="col">Outcome</th><th scope="col" className="num">p (correct)</th><th scope="col" className="num">Avg time</th><th scope="col" className="num">Discrimination</th><th scope="col">Review signals</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.quiz_id}-${r.question_id}`}>
                    <td className="lc-qa__text">
                      <span>{r.text}</span>
                      <span className="faint lc-small lc-block">
                        {!quizId && `${r.quiz_title} · `}Q{r.position} · {r.topic}
                        {r.reused && <> · <Repeat size={11} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-1px' }} /> reused in another quiz</>}
                      </span>
                    </td>
                    <td className="lc-small">
                      {DIFFICULTY_TEXT[r.difficulty]}
                      {r.enough_data && r.empirical_difficulty && r.empirical_difficulty !== r.difficulty && <span className="lc-warn lc-block">behaves {r.empirical_difficulty}</span>}
                    </td>
                    <td className="num">{r.answers}</td>
                    <td><OutcomeBar r={r} />{r.answers > 0 && <span className="faint lc-small lc-block">{pct01(r.pct_incorrect)} wrong · {pct01(r.pct_skipped)} skipped</span>}</td>
                    <td className="num">{!r.answers ? '—' : r.enough_data ? pct01(r.pct_correct) : <span className="faint" title={`Small sample: fewer than ${MIN_N} answers`}>{pct01(r.pct_correct)}*</span>}</td>
                    <td className="num">{r.avg_time_s != null ? duration(r.avg_time_s) : '—'}</td>
                    <td className="num">{r.discrimination != null ? r.discrimination.toFixed(2) : <span className="faint">—</span>}</td>
                    <td>
                      {!r.enough_data ? <span className="faint lc-small">Too few answers ({r.answers}/{MIN_N})</span>
                        : r.flags.length === 0 ? <span className="lc-ok lc-small">None</span>
                          : (
                            <ul className="list-plain lc-flags">
                              {r.flags.map((fl) => <li key={fl.code}><AlertTriangle size={12} aria-hidden="true" /> {fl.text}</li>)}
                            </ul>
                          )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="lc-legend lc-small" aria-label="Outcome legend" style={{ marginTop: 'var(--space-3)' }}>
            <li><span className="lc-swatch" style={{ background: 'var(--success)' }} aria-hidden="true" />Correct</li>
            <li><span className="lc-swatch" style={{ background: 'var(--error)' }} aria-hidden="true" />Incorrect</li>
            <li><span className="lc-swatch" style={{ background: 'var(--m-insufficient)' }} aria-hidden="true" />Skipped</li>
          </ul>
          <p className="faint lc-small" style={{ marginTop: 'var(--space-2)' }}>Discrimination is the correlation between getting this question right and the score on the rest of the quiz; higher means it separates stronger and weaker students. Negative values are flagged. * marks a percentage from fewer than {MIN_N} answers, too few to judge the question.</p>
        </Card>
      ))}
    </div>
  )
}
