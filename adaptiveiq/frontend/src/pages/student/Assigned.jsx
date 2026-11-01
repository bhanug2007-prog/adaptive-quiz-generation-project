import { useState } from 'react'
import { ClipboardList } from 'lucide-react'
import { Button, Card, EmptyState, ErrorState, LoadingBlock, PageHeader, Tabs } from '../../components/ui'
import { useApi } from '../../api/useApi'
import { studentApi } from '../../api/endpoints'
import QuizListItem from '../../components/student/QuizListItem'

const GROUPS = {
  todo: { label: 'To do', states: ['in_progress', 'open', 'late_open'] },
  upcoming: { label: 'Upcoming', states: ['upcoming'] },
  done: { label: 'Submitted', states: ['submitted'] },
  closed: { label: 'Closed', states: ['expired'] },
}
const EMPTY_TITLE = { todo: 'Nothing to do', upcoming: 'Nothing scheduled', done: 'Nothing submitted yet', closed: 'Nothing closed' }
const EMPTY = {
  todo: 'Nothing to do right now. New quizzes from your lecturers appear here when they open.',
  upcoming: 'No scheduled quizzes. Quizzes with a future opening time show up here.',
  done: 'You have not submitted an assigned quiz yet.',
  closed: 'No missed quizzes. Quizzes that closed before you attempted them are listed here.',
}

export default function Assigned() {
  const { data, error, loading, reload } = useApi(() => studentApi.assigned(), [])
  const [picked, setPicked] = useState(null)
  const firstNonEmpty = Object.keys(GROUPS).find((k) => (data || []).some((q) => GROUPS[k].states.includes(q.state))) || 'todo'
  const tab = picked || firstNonEmpty
  const setTab = setPicked
  const list = (data || []).filter((q) => GROUPS[tab].states.includes(q.state))
  return (
    <div className="st-page stack-lg">
      <PageHeader title="Assigned Quizzes" subtitle="Assessments from your lecturers. Every question has been reviewed by the lecturer before publishing." />
      {loading && !data ? <LoadingBlock rows={4} label="Loading assigned quizzes" /> : error ? (
        <ErrorState error={error} onRetry={reload} title="Could not load assigned quizzes" />
      ) : !data.length ? (
        <Card>
          <EmptyState icon={ClipboardList} title="No assigned quizzes yet" action={<Button to="/student/courses" variant="teal">Join a course</Button>}>
            When a lecturer in one of your courses publishes a quiz, it appears here with its due date and time limit.
          </EmptyState>
        </Card>
      ) : (
        <div className="stack">
          <Tabs label="Filter assigned quizzes" value={tab} onChange={setTab}
            tabs={Object.entries(GROUPS).map(([id, g]) => ({ id, label: `${g.label} (${data.filter((q) => g.states.includes(q.state)).length})` }))} />
          <div role="tabpanel" aria-label={GROUPS[tab].label}>
            {list.length ? (
              <ul className="st-quizlist">{list.map((q) => <QuizListItem key={q.id} quiz={q} />)}</ul>
            ) : <Card variant="flat"><EmptyState title={EMPTY_TITLE[tab]}>{EMPTY[tab]}</EmptyState></Card>}
          </div>
        </div>
      )}
    </div>
  )
}
