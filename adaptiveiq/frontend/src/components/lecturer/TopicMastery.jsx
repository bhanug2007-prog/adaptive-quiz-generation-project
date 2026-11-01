import { ArrowDownRight, ArrowRight, ArrowUpRight, Minus } from 'lucide-react'
import { EvidenceMeter, MasteryChip, ProgressBar } from '../ui'
import { LABELS, plural } from '../../utils/format'

const TREND_ICON = { improving: ArrowUpRight, declining: ArrowDownRight, stable: Minus, not_enough_data: Minus }

/** One topic's mastery estimate with the evidence behind it. t: lecturer student profile topic row. */
export default function TopicMasteryRow({ t }) {
  const judged = t.score_100 != null && t.label !== 'insufficient_evidence' && t.label !== 'not_attempted'
  const Trend = TREND_ICON[t.trend] || Minus
  return (
    <li className="lc-tm" style={{ '--tm': LABELS[t.label]?.color }}>
      <div className="lc-tm__head">
        <div>
          <strong>{t.topic}</strong>
          <span className="faint lc-small lc-block">{t.subject}</span>
        </div>
        <div className="lc-tm__score">
          {judged ? <span className="num"><b>{t.score_100}</b><span className="faint">/100</span></span>
            : t.label === 'insufficient_evidence' ? <span className="muted lc-small">No score yet</span> : null}
          <MasteryChip label={t.label} />
        </div>
      </div>
      {judged && <ProgressBar value={t.score_100} label={`${t.topic} estimated mastery`} />}
      <dl className="lc-tm__facts">
        <div>
          <dt>Evidence</dt>
          <dd>{t.answers === 0 ? 'No answers yet' : `${plural(t.unique_questions, 'question')} answered, ${t.correct} correct, ${t.incorrect} incorrect`}{t.skipped ? `, ${t.skipped} skipped` : ''}</dd>
        </div>
        <div>
          <dt>Confidence in the estimate</dt>
          <dd className="row" style={{ gap: 6 }}><EvidenceMeter level={t.evidence_level} />{t.evidence_text}</dd>
        </div>
        <div>
          <dt>Trend</dt>
          <dd title={t.trend_reason}><Trend size={13} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-2px' }} /> {t.trend_text}</dd>
        </div>
        <div>
          <dt>Next action</dt>
          <dd><ArrowRight size={13} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-2px', color: 'var(--teal)' }} /> {t.next_action_text}</dd>
        </div>
      </dl>
      {t.answers > 0 && <p className="faint lc-small">{[t.status_reason, t.trend_reason !== t.status_reason ? t.trend_reason : null].filter(Boolean).join(' ')}</p>}
    </li>
  )
}
