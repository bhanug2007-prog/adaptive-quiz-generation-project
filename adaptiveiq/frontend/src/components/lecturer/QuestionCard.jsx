import { Check, Cpu, FileText, Lock, ShieldAlert, ShieldCheck, ShieldQuestion, TriangleAlert } from 'lucide-react'
import { Badge } from '../ui'
import { DIFFICULTY_TEXT, dateTime } from '../../utils/format'
import { AI_CHECKS, MATH_TEXT, QUALITY, REVIEW, SOURCE_TEXT, formatSourceRef } from './util'

export function ReviewBadge({ status }) {
  const r = REVIEW[status] || { text: status }
  return <Badge tone={r.tone}>{r.text}</Badge>
}

const QUALITY_ICON = { passed: ShieldCheck, failed: ShieldAlert, not_checked: ShieldQuestion }

export function QualityBadge({ quality }) {
  if (!quality) return null
  const r = QUALITY[quality.status] || { text: quality.status }
  const label = quality.status === 'passed' && quality.score != null ? `${r.text} (${Math.round(quality.score)})` : r.text
  return <Badge tone={r.tone} icon={QUALITY_ICON[quality.status]} title={quality.ai_error || quality.reason_text || undefined}>{label}</Badge>
}

/** Why a question was kept although it failed, plus the AI reviewer's feedback. */
export function QualityNotice({ q }) {
  const v = q.validation || {}
  const ql = v.quality || {}
  if (!v.failed_validation && !(ql.status === 'failed') && !ql.stale) return null
  return (
    <div className="lc-quality" role="note">
      {v.failed_validation && (
        <p className="lc-quality__head"><TriangleAlert size={15} aria-hidden="true" />
          <span><strong>Failed checks: </strong>{v.failure_text || v.failure_reason}
            {v.failure_reason === 'quality_difficulty' && ql.assessed_difficulty ? ` (asked for ${q.difficulty}, judged ${ql.assessed_difficulty})` : ''}
            . It was kept so you can fix it. Edit or regenerate it, or reject it.</span>
        </p>
      )}
      {ql.feedback && <p className="lc-quality__fb"><strong>AI reviewer: </strong>{ql.feedback}</p>}
      {ql.stale && <p className="lc-quality__fb">Edited after the last check. Press Check again to review the new version.</p>}
    </div>
  )
}

/** What the automatic checks recorded for a question, plus where it came from. */
export function ValidationDetails({ q }) {
  const v = q.validation || {}
  const rows = []
  if (v.manual) rows.push(['Checks', 'Written by hand, no automatic checks'])
  if (v.math_status) rows.push(['Calculation check', MATH_TEXT[v.math_status] || v.math_status])
  if (v.max_similarity != null) rows.push(['Closest existing question', `${Math.round(v.max_similarity * 100)}% shared wording (TF-IDF, not meaning)`])
  if (v.grounding != null) rows.push(['Word overlap with reference', `${Math.round(v.grounding * 100)}% of key words found in the passage (not proof the passage supports it)`])
  const ql = v.quality
  if (ql) {
    rows.push(['AI review', ql.status === 'not_checked'
      ? `Not done: ${ql.ai_error || 'no reviewer available'}`
      : `${QUALITY[ql.status]?.text || ql.status}${ql.model ? ` by ${ql.model}` : ''}${ql.score != null ? `, score ${Math.round(ql.score)} / 100` : ''}`])
    if (ql.status === 'failed' && ql.reason_text) rows.push(['AI review reason', ql.reason_text])
    for (const [key, label, fmt] of AI_CHECKS) {
      const a = ql.ai?.[key]
      if (a) rows.push([label, a.note ? `${fmt(a)}. ${a.note}` : fmt(a)])
    }
  }
  const sourceRefLabel = formatSourceRef(q.source_ref || v.source)
  rows.push(['Source', SOURCE_TEXT[q.source_type] || q.source_type])
  if (sourceRefLabel) rows.push(['Source reference', sourceRefLabel])
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
  const sourceRefLabel = formatSourceRef(q.source_ref || q.validation?.source)
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
          {q.validation?.failed_validation && <Badge tone="error" icon={TriangleAlert}>Failed checks</Badge>}
          {q.review_status !== 'personal' && <QualityBadge quality={q.validation?.quality} />}
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
      {!compact && sourceRefLabel && (
        <p className="lc-q__source">
          <FileText size={14} aria-hidden="true" />
          <span><strong>Source: </strong>{sourceRefLabel}</span>
        </p>
      )}
      {!compact && q.review_status !== 'personal' && <QualityNotice q={q} />}
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
