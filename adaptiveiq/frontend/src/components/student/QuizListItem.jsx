import { CalendarClock, ChevronRight, Clock, FileQuestion, Trophy, User } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button } from '../ui'
import { dateTime, pct, plural, relative } from '../../utils/format'
import { KindBadge, QuizStateBadge } from './Badges'
import { attemptsLeft, quizAction } from './helpers'

/** One quiz card (assigned or practice) in a list, with every field the student needs before starting. */
export default function QuizListItem({ quiz }) {
  const action = quizAction(quiz)
  const left = attemptsLeft(quiz)
  const href = `/student/quizzes/${quiz.id}`
  const due = quiz.due_at || quiz.closes_at
  return (
    <li className="st-quiz card card--flat" data-state={quiz.state}>
      <div className="st-quiz__main">
        <div className="row" style={{ gap: 8 }}>
          <QuizStateBadge state={quiz.state} />
          {quiz.kind === 'practice' && <KindBadge kind="practice" />}
          {quiz.graded && quiz.kind === 'assessment' && quiz.contribution_pct > 0 && (
            <span className="badge">Counts {quiz.contribution_pct}% of the subject grade</span>
          )}
        </div>
        <h3 className="st-quiz__title"><Link to={href} className="st-quiz__link">{quiz.title}</Link></h3>
        <p className="st-quiz__sub">
          {[quiz.course_title, quiz.subject && quiz.subject !== quiz.course_title ? quiz.subject : null, quiz.topics?.join(', ')].filter(Boolean).join(' · ')}
        </p>
        <ul className="st-quiz__meta">
          {quiz.lecturer && <li><User size={14} aria-hidden="true" />{quiz.lecturer}</li>}
          <li><FileQuestion size={14} aria-hidden="true" />{plural(quiz.question_count, 'question')} · {quiz.max_marks} marks</li>
          {quiz.time_limit_min ? <li><Clock size={14} aria-hidden="true" />{quiz.time_limit_min} min limit</li> : <li><Clock size={14} aria-hidden="true" />No time limit</li>}
          {quiz.state === 'upcoming' && quiz.opens_at && <li><CalendarClock size={14} aria-hidden="true" />Opens {dateTime(quiz.opens_at)}</li>}
          {due && quiz.state !== 'upcoming' && (
            <li><CalendarClock size={14} aria-hidden="true" />{quiz.due_at ? 'Due' : 'Closes'} {dateTime(due)} <span className="faint">({relative(due)})</span></li>
          )}
          {!due && quiz.kind === 'assessment' && <li><CalendarClock size={14} aria-hidden="true" />No due date</li>}
          {quiz.best_percentage != null && <li><Trophy size={14} aria-hidden="true" />Best {pct(quiz.best_percentage)}</li>}
        </ul>
      </div>
      <div className="st-quiz__side">
        {left != null && <span className="st-quiz__attempts num">{left} of {quiz.attempts_allowed} attempts left</span>}
        {quiz.kind === 'practice' && quiz.attempts_used > 0 && <span className="st-quiz__attempts num">{plural(quiz.attempts_used, 'attempt')}</span>}
        <Button to={!action && quiz.last_session_id ? `/student/attempts/${quiz.last_session_id}/result` : href} variant={action?.primary ? 'teal' : 'secondary'} size="sm" iconRight={ChevronRight}
          aria-label={`${action?.label || 'Details'}: ${quiz.title}`}>
          {action?.label || (quiz.last_session_id ? 'View result' : 'Details')}
        </Button>
      </div>
    </li>
  )
}
