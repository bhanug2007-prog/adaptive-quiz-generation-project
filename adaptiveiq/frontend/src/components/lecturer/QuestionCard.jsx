import { Check, Cpu, Lock } from 'lucide-react'
import { Badge } from '../ui'
import { DIFFICULTY_TEXT, dateTime } from '../../utils/format'
import { MATH_TEXT, REVIEW, SOURCE_TEXT } from './util'

export function ReviewBadge({ status }) {
  const r = REVIEW[status] || { text: status }
  return <Badge tone={r.tone}>{r.text}</Badge>
}

/** What the automatic checks recorded for a question, plus where it came from. */
export function ValidationDetails({ q }) {
  const v = q.validation || {}
  const rows = []
  if (v.manual) rows.push(['Checks', 'Written by hand, no automatic checks'])
  if (v.math_status) rows.push(['Calculation check', MATH_TEXT[v.math_status] || v.math_status])
  if (v.max_similarity != null) rows.push(['Closest existing question', `${Math.round(v.max_similarity * 100)}% shared wording (TF-IDF, not meaning)`])
  if (v.grounding != null) rows.push(['Word overlap with reference', `${Math.round(v.grounding * 100)}% of key words found in the passage (not proof the passage supports it)`])
  rows.push(['Source', SOURCE_TEXT[q.source_type] || q.source_type])
  rows.push(['Model', q.model || 'None (not generated)'])
  rows.push(['Created', dateTime(q.created_at)])
  rows.push(['Used in quizzes', String(q.used_in_quizzes ?? 0)])
  rows.push(['Student answers', String(q.answered_count ?? 0)])
  return (
    <div className="stack" style={{ gap: 'var(--space-3)' }}>
      <dl className="lc-dl">
        {rows.map(([k, val]) => (
          <div key={k}><dt>{k}</dt><dd>{val}</dd></div>
        ))}
      </dl>
      {q.source_excerpt && (
        <div>
          <p className="lc-mini-label">Source excerpt the model was given</p>
          <blockquote className="lc-excerpt">{q.source_excerpt}</blockquote>
        </div>
      )}
    </div>
  )
}

export default function QuestionCard({ q, index, actions, children, compact }) {
  return (
    <article className="lc-q" data-status={q.review_status} aria-label={index != null ? `Question ${index}` : 'Question'}>
      <header className="lc-q__head">
        <div className="row" style={{ gap: 'var(--space-2)' }}>
          {index != null && <span className="lc-q__num">Q{index}</span>}
          <ReviewBadge status={q.review_status} />
          <Badge>{DIFFICULTY_TEXT[q.difficulty] || q.difficulty}</Badge>
          <span className="faint lc-q__topic">{q.topic_label}</span>
          {q.model && <Badge tone="accent" icon={Cpu} title={q.model}>AI-generated</Badge>}
          {q.locked && <Badge icon={Lock} title="Students have answered it">Locked</Badge>}
        </div>
      </header>
      <p className="lc-q__text">{q.text}</p>
      <ol className="lc-q__opts">
        {q.options.map((o) => (
          <li key={o.id} data-correct={o.is_correct || undefined}>
            <span className="lc-q__letter" aria-hidden="true">{o.label}</span>
            <span className="lc-q__opt-text">{o.text}</span>
            {o.is_correct && <span className="lc-q__key"><Check size={14} aria-hidden="true" /> Correct answer</span>}
          </li>
        ))}
      </ol>
      {!compact && q.explanation && <p className="lc-q__expl"><strong>Explanation: </strong>{q.explanation}</p>}
      {!compact && (
        <details className="lc-details">
          <summary>Checks, source and model</summary>
          <ValidationDetails q={q} />
        </details>
      )}
      {children}
      {actions && <div className="lc-q__actions">{actions}</div>}
    </article>
  )
}
