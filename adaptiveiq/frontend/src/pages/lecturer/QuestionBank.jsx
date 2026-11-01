import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronLeft, ChevronRight, Library, Plus, Search } from 'lucide-react'
import { lecturerApi, topicsApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Badge, Button, Dialog, EmptyState, ErrorState, Field, Input, LoadingBlock, PageHeader, Select, useToast } from '../../components/ui'
import { DIFFICULTY_TEXT, date, plural } from '../../utils/format'
import QuestionReview from '../../components/lecturer/QuestionReview'
import QuestionEditor from '../../components/lecturer/QuestionEditor'
import { ReviewBadge } from '../../components/lecturer/QuestionCard'

const PAGE = 20

export default function QuestionBank() {
  const [f, setF] = useState({ q: '', course_id: '', topic_id: '', difficulty: '', review_status: '' })
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState(null)
  const [creating, setCreating] = useState(false)
  const { notify } = useToast()
  const courses = useApi(() => lecturerApi.courses(), [])
  const topics = useApi(() => topicsApi.choices(), [])

  useEffect(() => {
    const t = setTimeout(() => { setF((s) => (s.q === search ? s : { ...s, q: search })); setPage(1) }, 300)
    return () => clearTimeout(t)
  }, [search])

  const params = { ...f, page, page_size: PAGE }
  const list = useApi(() => lecturerApi.questions(params), [JSON.stringify(params)])
  const set = (k) => (e) => { setF((s) => ({ ...s, [k]: e.target.value, ...(k === 'course_id' ? { topic_id: '' } : {}) })); setPage(1) }

  const topicList = useMemo(() => (topics.data || []).filter((t) => !f.course_id || String(t.course_id) === f.course_id), [topics.data, f.course_id])
  const topicChoices = (topics.data || []).map((t) => ({ topic_id: t.topic_id, label: `${t.course} › ${t.subject} › ${t.unit} › ${t.topic}`, objectives: t.objectives }))
  const objectivesFor = (q) => (topics.data || []).find((t) => t.topic_id === q.topic_id)?.objectives || []

  const replace = (nq) => list.setData((d) => ({ ...d, items: d.items.map((x) => (x.id === nq.id ? nq : x)) }))
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE)) : 1
  const filtered = Object.values(f).some(Boolean)

  return (
    <div className="lc-page">
      <PageHeader eyebrow="Question bank" title="Question bank"
        subtitle="Every question you have generated or written. Review, edit, reuse in quizzes, and see where each came from."
        actions={<Button variant="primary" icon={Plus} onClick={() => setCreating(true)} disabled={!topics.data?.length}
          title={topics.data && !topics.data.length ? 'Add a topic to a course first' : undefined}>Write a question</Button>} />

      <div className="lc-filters" role="search">
        <Field label="Search">
          {(a) => (
            <div className="lc-search">
              <Search size={15} aria-hidden="true" />
              <Input {...a} type="search" placeholder="Question text or topic" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
          )}
        </Field>
        <Field label="Course">
          {(a) => (
            <Select {...a} value={f.course_id} onChange={set('course_id')}>
              <option value="">All courses</option>
              {(courses.data || []).map((c) => <option key={c.id} value={c.id}>{c.code} · {c.title}</option>)}
            </Select>
          )}
        </Field>
        <Field label="Topic">
          {(a) => (
            <Select {...a} value={f.topic_id} onChange={set('topic_id')}>
              <option value="">All topics</option>
              {topicList.map((t) => <option key={t.topic_id} value={t.topic_id}>{t.topic} ({t.unit})</option>)}
            </Select>
          )}
        </Field>
        <Field label="Difficulty">
          {(a) => (
            <Select {...a} value={f.difficulty} onChange={set('difficulty')}>
              <option value="">Any</option>
              <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
            </Select>
          )}
        </Field>
        <Field label="Review status">
          {(a) => (
            <Select {...a} value={f.review_status} onChange={set('review_status')}>
              <option value="">Any</option>
              <option value="draft">Needs review</option><option value="approved">Approved</option><option value="rejected">Rejected</option>
            </Select>
          )}
        </Field>
      </div>

      {list.loading && !list.data && <LoadingBlock rows={4} label="Loading questions" />}
      {list.error && <ErrorState error={list.error} onRetry={list.reload} />}
      {list.data && (list.data.items.length === 0 ? (
        filtered ? (
          <EmptyState icon={Search} title="No questions match" action={<Button onClick={() => { setSearch(''); setF({ q: '', course_id: '', topic_id: '', difficulty: '', review_status: '' }) }}>Clear filters</Button>}>
            Try a different search or remove a filter.
          </EmptyState>
        ) : (
          <EmptyState icon={Library} title="Your question bank is empty" action={<Button variant="primary" to="/lecturer/create">Generate a quiz</Button>}>
            Questions appear here when you generate a quiz or write one by hand.
          </EmptyState>
        )
      ) : (
        <div className="stack" aria-busy={list.loading || undefined}>
          <p className="muted lc-small" aria-live="polite">{plural(list.data.total, 'question')}{filtered ? ' match' : ''}</p>
          <ul className="list-plain lc-bank">
            {list.data.items.map((q) => {
              const isOpen = open === q.id
              return (
                <li key={q.id} className="lc-bank__item" data-open={isOpen || undefined}>
                  <button type="button" className="lc-bank__row" aria-expanded={isOpen} aria-controls={`q-${q.id}`} onClick={() => setOpen(isOpen ? null : q.id)}>
                    <span className="lc-bank__text">{q.text}</span>
                    <span className="lc-bank__meta">
                      <ReviewBadge status={q.review_status} />
                      <Badge>{DIFFICULTY_TEXT[q.difficulty]}</Badge>
                      <span className="faint">{q.topic_label}</span>
                      <span className="faint">{q.used_in_quizzes ? `In ${plural(q.used_in_quizzes, 'quiz', 'quizzes')}` : 'Not used yet'}</span>
                      <span className="faint">{date(q.created_at)}</span>
                    </span>
                    <ChevronDown size={16} aria-hidden="true" className="lc-bank__chev" />
                  </button>
                  {isOpen && (
                    <div id={`q-${q.id}`} className="lc-bank__body appear">
                      <QuestionReview q={q} objectives={objectivesFor(q)} onChanged={replace}
                        onDuplicated={() => list.reload()} onDeleted={() => { setOpen(null); list.reload() }} />
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
          {pages > 1 && (
            <nav className="lc-pager" aria-label="Pages">
              <Button size="sm" icon={ChevronLeft} disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <span className="lc-small muted">Page {page} of {pages}</span>
              <Button size="sm" iconRight={ChevronRight} disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
            </nav>
          )}
        </div>
      ))}

      <Dialog open={creating} onClose={() => setCreating(false)} title="Write a question" wide
        description="Questions you write are approved straight away and can be added to any draft quiz in the same course.">
        {creating && (
          <QuestionEditor topics={topicChoices} submitLabel="Add to bank" onCancel={() => setCreating(false)}
            onSubmit={async (body) => {
              await lecturerApi.createQuestion(body)
              notify('Question added to the bank')
              setCreating(false)
              list.reload()
            }} />
        )}
      </Dialog>
    </div>
  )
}
