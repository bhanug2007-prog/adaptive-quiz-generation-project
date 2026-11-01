import { ArrowDownRight, ArrowRight, ArrowUpRight, Minus, FlaskConical } from 'lucide-react'
import { Button, EvidenceMeter, MasteryChip } from '../ui'
import { LABELS, relative } from '../../utils/format'
import Expandable from './Expandable'
import { evidenceSentence, isInsufficient, practiceHref } from './helpers'

const TREND_ICON = { improving: ArrowUpRight, declining: ArrowDownRight, stable: Minus }

/** Score with its likely range, drawn as a band on a 0-100 track. */
export function MasteryBand({ topic }) {
  const has = topic.score != null && !isInsufficient(topic)
  const lo = has ? Math.round((topic.lower ?? topic.score) * 100) : 0
  const hi = has ? Math.round((topic.upper ?? topic.score) * 100) : 0
  const v = has ? topic.score_100 : 0
  const color = (LABELS[topic.label] || LABELS.not_attempted).color
  return (
    <div className="st-band" aria-hidden="true" style={{ '--band-color': color }}>
      <div className="st-band__range" style={{ left: `${lo}%`, width: `${Math.max(hi - lo, 0)}%` }} />
      <div className="st-band__value" style={{ left: `${v}%`, opacity: has ? 1 : 0 }} />
    </div>
  )
}

/** One topic's mastery estimate with the evidence behind it, its trend and the suggested next step. */
export default function TopicMasteryCard({ topic, compact, showPractice = true }) {
  const insufficient = isInsufficient(topic)
  const TrendIcon = TREND_ICON[topic.trend]
  return (
    <article className="st-topic card card--flat" data-label={topic.label}>
      <header className="st-topic__head">
        <div style={{ minWidth: 0 }}>
          <p className="st-topic__subject">{topic.subject || 'Practice topic'}</p>
          <h3 className="st-topic__name">{topic.topic}</h3>
        </div>
        <MasteryChip label={topic.label} />
      </header>

      <div className="st-topic__score">
        {insufficient ? (
          <p className="st-topic__insufficient">
            {topic.answers ? 'Insufficient evidence for an estimate' : 'No answers yet'}
          </p>
        ) : (
          <p className="st-topic__num num" aria-label={`Estimated mastery ${topic.score_100} out of 100`}>
            {topic.score_100}<span>/100</span>
          </p>
        )}
        {!insufficient && topic.lower != null && (
          <span className="st-topic__range faint num">likely {Math.round(topic.lower * 100)}–{Math.round(topic.upper * 100)}</span>
        )}
      </div>
      <MasteryBand topic={topic} />

      <dl className="st-topic__facts">
        <div>
          <dt>Evidence</dt>
          <dd>
            <span className="row" style={{ gap: 8 }}>
              <EvidenceMeter level={topic.evidence_level} />
              <span>{topic.evidence_text}</span>
            </span>
            <span className="st-topic__small">{evidenceSentence(topic)}</span>
          </dd>
        </div>
        <div>
          <dt>Trend</dt>
          <dd>
            <span className={`st-trend st-trend--${topic.trend}`}>
              {TrendIcon && <TrendIcon size={14} aria-hidden="true" />}
              {topic.trend_text}
            </span>
            {!compact && <span className="st-topic__small">{topic.trend_reason}</span>}
          </dd>
        </div>
        <div className="st-topic__next">
          <dt>Next step</dt>
          <dd>{topic.next_action_text}</dd>
        </div>
      </dl>

      <footer className="st-topic__foot">
        {topic.last_activity ? <span className="faint st-topic__small">Last answered {relative(topic.last_activity)}</span> : <span />}
        {showPractice && (
          <Button size="sm" variant="teal" icon={FlaskConical} iconRight={ArrowRight}
            to={practiceHref({ subject: topic.subject, topic: topic.topic, topic_id: topic.topic_id, difficulty: topic.next_difficulty })}
            aria-label={`Practise ${topic.topic}`}>
            Practise
          </Button>
        )}
      </footer>
      {!compact && topic.explanation && (
        <Expandable label="How this estimate was made" openLabel="Hide details">
          <p className="st-topic__small">{topic.explanation}</p>
        </Expandable>
      )}
    </article>
  )
}
