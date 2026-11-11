import { useState } from 'react'
import { Bot, CheckCircle2, ChevronDown, GitBranch, Wrench, XCircle } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { Badge, Button, ErrorState, LoadingBlock } from '../ui'

/** Plain names for the agents' tools and decisions (anything unknown is shown as it is). */
export const STEP_TEXT = {
  // Question Quality Agent
  prepare_contexts: 'Prepare the source material',
  plan: 'Plan the difficulty of each question',
  generate_questions: 'Generate a question (Qwen)',
  regenerate_question: 'Regenerate the question (Qwen)',
  validate_question: 'Python checks',
  check_duplicate_questions: 'Duplicate check',
  evaluate_question_quality: 'AI quality review',
  save_question_draft: 'Save as a draft question',
  check_difficulty_distribution: 'Check the difficulty mix',
  get_generation_status: 'Read the run status',
  accept: 'Accept the question',
  retry: 'Try this question again',
  give_up: 'No tries left',
  keep_as_failed: 'Keep for review, marked "Failed checks"',
  drop: 'Save nothing for this question',
  stop: 'Stop the run',
  report_mix: 'Report the difficulty mix',
  await_lecturer_approval: 'Wait for your review (never publishes)',
  // Lecturer Insights Agent
  plan_tools: 'AI picks the tools',
  use_ai_plan: 'Use the AI’s choice',
  route_by_keywords: 'Pick tools by keywords',
  refuse_tool: 'Refuse a tool call',
  refuse_args: 'Remove arguments',
  limit_tools: 'Limit the number of tools',
  get_class_analytics: 'Read class analytics',
  get_topic_mastery: 'Read topic mastery',
  get_question_statistics: 'Read question statistics',
  get_student_performance: 'Read student performance (anonymised)',
  get_assessment_results: 'Read assessment results',
  create_lecturer_report: 'Build a course report',
  write_answer: 'AI writes the answer',
  accept_answer: 'Accept the AI’s answer',
  reject_answer: 'Reject the AI’s answer',
  out_of_scope: 'Question is not about this course',
  no_data: 'No data found',
}

const KIND = { tool: { text: 'Tool', icon: Wrench }, decision: { text: 'Decision', icon: GitBranch }, llm: { text: 'AI call', icon: Bot } }

function detail(s) {
  const r = s.result || {}
  if (r.because) return r.because
  if (r.error) return r.error
  const bits = Object.entries(r).filter(([, v]) => v !== null && v !== undefined && v !== '' && typeof v !== 'object')
    .slice(0, 5).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
  return bits.join(' · ')
}

function where(s) {
  const a = s.args || {}
  const bits = []
  if (a.slot) bits.push(`question ${a.slot}`)
  if (a.try) bits.push(`try ${a.try}`)
  if (a.difficulty) bits.push(a.difficulty)
  if (a.quiz_id) bits.push(`quiz ${a.quiz_id}`)
  return bits.join(', ')
}

/** The ordered list of what an agent did: tools it ran, AI calls, and each decision with its reason. */
export function StepList({ steps }) {
  if (!steps?.length) return <p className="muted lc-small">No steps were recorded.</p>
  return (
    <ol className="list-plain lc-steps">
      {steps.map((s) => {
        const K = KIND[s.kind] || KIND.tool
        return (
          <li key={s.seq} className="lc-step" data-kind={s.kind} data-ok={s.ok ? 'true' : 'false'}>
            <span className="lc-step__icon" aria-hidden="true">{s.ok ? <K.icon size={14} /> : <XCircle size={14} />}</span>
            <div>
              <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                <strong>{STEP_TEXT[s.name] || s.name}</strong>
                <Badge tone={s.kind === 'decision' ? 'accent' : undefined}>{K.text}</Badge>
                {!s.ok && <Badge tone="error">Failed</Badge>}
                {where(s) && <span className="faint lc-small">{where(s)}</span>}
                {s.duration_ms != null && s.duration_ms > 0 && <span className="faint lc-small">{s.duration_ms} ms</span>}
              </div>
              {detail(s) && <p className="faint lc-small">{detail(s)}</p>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/** A collapsed "what the agent did" section that loads the step log when opened. */
export default function AgentLog({ load, title = 'What the agent did', summary }) {
  const [open, setOpen] = useState(false)
  const [state, setState] = useState({ loading: false, data: null, error: null })
  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (next && !state.data) {
      setState({ loading: true, data: null, error: null })
      try { setState({ loading: false, data: await load(), error: null }) } catch (e) { setState({ loading: false, data: null, error: e }) }
    }
  }
  const run = state.data
  return (
    <div className="lc-agentlog">
      <Button size="sm" variant="ghost" icon={ChevronDown} aria-expanded={open} onClick={toggle}
        className={open ? 'lc-agentlog__btn is-open' : 'lc-agentlog__btn'}>{title}</Button>
      {open && (
        <div className="lc-agentlog__body">
          {summary && <p className="faint lc-small">{summary}</p>}
          {state.loading && <LoadingBlock rows={2} label="Loading the step log" />}
          {state.error && <ErrorState error={state.error} onRetry={() => { setOpen(false); setState({ loading: false, data: null, error: null }) }} />}
          {run && (
            <>
              <p className="faint lc-small">
                <CheckCircle2 size={12} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-1px' }} />{' '}
                {run.steps.length} steps · {run.llm_calls} AI {run.llm_calls === 1 ? 'call' : 'calls'} · status {run.status}
              </p>
              <StepList steps={run.steps} />
            </>
          )}
        </div>
      )}
    </div>
  )
}

export const generationLog = (runId) => () => lecturerApi.generationAgent(runId)
export const agentRunLog = (id) => () => lecturerApi.agentRun(id)
