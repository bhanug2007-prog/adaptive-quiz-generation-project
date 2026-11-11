import { useState } from 'react'
import { MessageSquareText, Send } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Alert, Badge, Button, Card, Field, Select, Textarea } from '../ui'
import AgentLog, { STEP_TEXT, agentRunLog } from './AgentSteps'
import { errText } from './util'

const EXAMPLES = [
  'Which topics is the class weakest in?',
  'Which students may need support?',
  'Which questions were most often answered wrongly?',
  'How did the last quiz go?',
]

/** "Ask about your class": the Lecturer Insights Agent. Read-only; answers from the course's own data. */
export default function AskClass({ courseId }) {
  const quizzes = useApi(() => lecturerApi.quizzes({ course_id: courseId }), [courseId])
  const [question, setQuestion] = useState('')
  const [quizId, setQuizId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [answer, setAnswer] = useState(null)

  const ask = async (e) => {
    e?.preventDefault()
    const q = question.trim()
    if (q.length < 3) { setError('Type a question first.'); return }
    setBusy(true)
    setError(null)
    try {
      setAnswer(await lecturerApi.askClass({ course_id: Number(courseId), quiz_id: quizId ? Number(quizId) : null, question: q }))
    } catch (err) {
      setError(errText(err))
    } finally {
      setBusy(false)
    }
  }

  const published = (quizzes.data || []).filter((z) => z.status === 'published' || z.status === 'archived')
  return (
    <div className="stack-lg">
      <Card title={<span className="row" style={{ gap: 8 }}><MessageSquareText size={16} aria-hidden="true" style={{ color: 'var(--accent)' }} />Ask about your class</span>}
        subtitle="The answer comes only from this course's recorded quizzes, answers and mastery. Students are sent to the AI as Student 1, Student 2…, never by name; names are shown only to you. The agent cannot change anything.">
        <form className="stack" onSubmit={ask}>
          <Field label="Your question" hint="Up to 500 characters.">
            {(a) => <Textarea {...a} rows={2} maxLength={500} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. Which topics should I revisit next week?" />}
          </Field>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            {EXAMPLES.map((x) => <button key={x} type="button" className="lc-chip" onClick={() => setQuestion(x)}>{x}</button>)}
          </div>
          <div className="row" style={{ gap: 'var(--space-3)', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <Field label="Quiz (optional)">
              {(a) => <Select {...a} value={quizId} onChange={(e) => setQuizId(e.target.value)}><option value="">Whole course</option>{published.map((z) => <option key={z.id} value={z.id}>{z.title}</option>)}</Select>}
            </Field>
            <Button type="submit" variant="primary" icon={Send} loading={busy}>Ask</Button>
          </div>
          {error && <Alert tone="error">{error}</Alert>}
        </form>
      </Card>
      {answer && <Answer a={answer} />}
    </div>
  )
}

function Answer({ a }) {
  const tools = a.tools_used || []
  return (
    <Card className="lc-answer appear" title="Answer" subtitle={a.question}>
      <div className="stack">
        <p className="lc-answer__text">{a.answer}</p>
        {a.findings?.length > 0 && (
          <section><h4 className="lc-answer__h">What the data shows</h4><ul className="lc-answer__list">{a.findings.map((x, i) => <li key={i}>{x}</li>)}</ul></section>
        )}
        {a.suggestions?.length > 0 && (
          <section><h4 className="lc-answer__h">Suggestions</h4><ul className="lc-answer__list">{a.suggestions.map((x, i) => <li key={i}>{x}</li>)}</ul></section>
        )}
        {a.caveats?.length > 0 && (
          <Alert tone="info" title="Limits of this answer"><ul className="lc-answer__list">{a.caveats.map((x, i) => <li key={i}>{x}</li>)}</ul></Alert>
        )}
        <div className="lc-answer__how">
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            <Badge tone={a.mode === 'ai' ? 'accent' : undefined}>{a.mode === 'ai' ? `Worded by AI${a.model ? ` (${a.model})` : ''}` : 'Fixed rules (no AI)'}</Badge>
            {tools.map((t, i) => <Badge key={i} tone={t.ok ? undefined : 'error'}>{STEP_TEXT[t.name] || t.name}{t.args?.quiz_id ? ` · quiz ${t.args.quiz_id}` : ''}</Badge>)}
            {tools.length === 0 && <span className="faint lc-small">No data tools were run.</span>}
          </div>
          {a.ai_note && <p className="faint lc-small">AI not used: {a.ai_note}</p>}
          {a.mode === 'ai' && <p className="faint lc-small">Every number in this answer was checked against the data before it was shown.</p>}
          <AgentLog load={agentRunLog(a.agent_run_id)} title="Show the agent's steps" />
        </div>
      </div>
    </Card>
  )
}
