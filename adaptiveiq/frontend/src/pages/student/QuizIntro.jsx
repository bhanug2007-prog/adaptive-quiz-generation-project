import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, CalendarClock, CheckCircle2, Clock, FileQuestion, Keyboard, Play, RotateCcw, Save, Target, Trophy, User } from 'lucide-react'
import { Alert, Button, Card, ErrorState, LoadingBlock, PageHeader } from '../../components/ui'
import { useApi } from '../../api/useApi'
import { studentApi } from '../../api/endpoints'
import { dateTime, pct, plural, relative } from '../../utils/format'
import { KindBadge, QuizStateBadge } from '../../components/student/Badges'
import { attemptsLeft, quizAction } from '../../components/student/helpers'

function Fact({ icon: Icon, label, children }) {
  return (
    <div className="st-fact">
      <Icon size={16} aria-hidden="true" />
      <div><dt>{label}</dt><dd>{children}</dd></div>
    </div>
  )
}

export default function QuizIntro() {
  const { quizId } = useParams()
  const navigate = useNavigate()
  const { data: q, error, loading, reload } = useApi(() => studentApi.quiz(quizId), [quizId])
  const [busy, setBusy] = useState(false)
  const [startErr, setStartErr] = useState(null)
  const back = q?.kind === 'practice' ? { to: '/student/practice', label: 'Practice Lab' } : { to: '/student/assigned', label: 'Assigned quizzes' }

  if (loading && !q) return <LoadingBlock rows={4} label="Loading quiz" />
  if (error) return <ErrorState error={error} onRetry={reload} title={error.status === 404 ? 'Quiz not found' : 'Could not load this quiz'} />

  const action = quizAction(q)
  const left = attemptsLeft(q)
  const start = async () => {
    setBusy(true)
    setStartErr(null)
    try {
      const s = await studentApi.start(q.id)
      navigate(`/student/attempts/${s.session_id}`)
    } catch (e) {
      setStartErr(e)
      setBusy(false)
      reload()
    }
  }

  return (
    <div className="st-page st-narrow stack-lg">
      <Link to={back.to} className="st-back"><ArrowLeft size={15} aria-hidden="true" />{back.label}</Link>
      <PageHeader eyebrow={[q.course_title, q.subject].filter((x, i, a) => x && a.indexOf(x) === i).join(' · ') || (q.kind === 'practice' ? 'Practice' : 'Assessment')}
        title={q.title} />
      <div className="row" style={{ marginTop: -12 }}>
        <QuizStateBadge state={q.state} />
        <KindBadge kind={q.kind} long />
      </div>

      <Card>
        <dl className="st-facts">
          <Fact icon={FileQuestion} label="Questions">{plural(q.question_count, 'question')} · {q.max_marks} marks in total</Fact>
          <Fact icon={Clock} label="Time limit">{q.time_limit_min ? `${q.time_limit_min} minutes from when you start` : 'No time limit'}</Fact>
          {q.kind === 'assessment' && (
            <Fact icon={RotateCcw} label="Attempts">
              {q.attempts_allowed ? `${left} of ${q.attempts_allowed} left` : `Unlimited · ${plural(q.attempts_used, 'attempt')} used`}
            </Fact>
          )}
          {q.kind === 'practice' && <Fact icon={RotateCcw} label="Attempts">Unlimited · {plural(q.attempts_used, 'attempt')} so far</Fact>}
          {q.opens_at && <Fact icon={CalendarClock} label="Opens">{dateTime(q.opens_at)}</Fact>}
          {q.kind === 'assessment' && (
            <Fact icon={CalendarClock} label="Due">{q.due_at ? <>{dateTime(q.due_at)} <span className="faint">({relative(q.due_at)})</span></> : 'No due date'}</Fact>
          )}
          {q.closes_at && <Fact icon={CalendarClock} label="Closes">{dateTime(q.closes_at)}</Fact>}
          {q.topics?.length > 0 && <Fact icon={Target} label={q.topics.length > 1 ? 'Topics' : 'Topic'}>{q.topics.join(', ')}</Fact>}
          {q.lecturer && <Fact icon={User} label="Lecturer">{q.lecturer}</Fact>}
          {q.kind === 'assessment' && (
            <Fact icon={Trophy} label="Grade">{q.graded && q.contribution_pct ? `Counts ${q.contribution_pct}% towards the subject grade` : 'Not counted towards your grade'}</Fact>
          )}
          {q.best_percentage != null && <Fact icon={CheckCircle2} label="Your best">{pct(q.best_percentage)}</Fact>}
        </dl>
      </Card>

      <Card title="Before you start" variant="flat">
        <ul className="st-rules">
          <li><Save size={15} aria-hidden="true" />Every answer is saved as soon as you choose it. If you refresh or lose connection, you can resume where you left off.</li>
          {q.time_limit_min ? <li><Clock size={15} aria-hidden="true" />The timer keeps running if you leave. When time is up, your saved answers are submitted automatically.</li> : null}
          {q.kind === 'practice'
            ? <li><CheckCircle2 size={15} aria-hidden="true" />In practice you can check each answer as you go. Checking shows the correct option and locks that answer.</li>
            : <li><CheckCircle2 size={15} aria-hidden="true" />Correct answers are not shown during the quiz. You see them on the result page once your lecturer releases feedback.</li>}
          {q.state === 'late_open' && <li className="st-rules__warn"><CalendarClock size={15} aria-hidden="true" />The due date has passed. A late submission may receive a penalty.</li>}
          <li><Keyboard size={15} aria-hidden="true" />Keyboard: press 1–4 or A–D to choose, and the arrow keys to move between questions.</li>
        </ul>
      </Card>

      {startErr && <Alert tone="error" title="Could not start">{startErr.message}</Alert>}
      <div className="row">
        {action && <Button variant={q.kind === 'practice' ? 'primary' : 'teal'} size="lg" icon={Play} onClick={start} loading={busy}>{action.label}</Button>}
        {!action && q.state === 'upcoming' && <Alert tone="info">This quiz opens {q.opens_at ? `${dateTime(q.opens_at)} (${relative(q.opens_at)})` : 'later'}.</Alert>}
        {!action && q.state === 'expired' && <Alert tone="warning">This quiz has closed. It can no longer be attempted.</Alert>}
        {!action && q.state === 'submitted' && q.kind === 'assessment' && <span className="muted">You have used all your attempts.</span>}
        {q.last_session_id && <Button variant="secondary" size="lg" to={`/student/attempts/${q.last_session_id}/result`}>View last result</Button>}
      </div>
    </div>
  )
}
