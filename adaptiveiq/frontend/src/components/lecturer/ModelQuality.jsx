import { Cpu, FlaskConical } from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import { Alert, Badge, Button, Card, EmptyState, ErrorState, LoadingBlock } from '../ui'
import { duration, pct01, plural } from '../../utils/format'

/** Below this many questions (or model calls) a rate is shown with a "small sample" warning. */
export const SMALL_N = 30

function Rate({ label, value, of, hint }) {
  return (
    <div className="lc-rate">
      <span className="lc-rate__label">{label}</span>
      <span className="lc-rate__value num">{value == null ? '—' : pct01(value, 0)}</span>
      <span className="lc-rate__hint">{value == null ? 'No data yet' : hint || of}</span>
    </div>
  )
}

function Count({ label, value, hint }) {
  return (
    <div className="lc-rate">
      <span className="lc-rate__label">{label}</span>
      <span className="lc-rate__value num">{value ?? '—'}</span>
      {hint && <span className="lc-rate__hint">{hint}</span>}
    </div>
  )
}

function VersionCard({ v }) {
  const reviewed = v.approved + v.rejected
  const small = v.questions < SMALL_N || v.model_calls < SMALL_N
  const maxRej = Math.max(1, ...v.rejected_by_check.map((r) => r.count))
  const variantTone = v.variant === 'finetuned' ? 'accent' : undefined
  return (
    <Card className="lc-mq" title={<span className="row" style={{ gap: 8 }}><Cpu size={16} aria-hidden="true" style={{ color: 'var(--accent)' }} />{v.name}</span>}
      subtitle={[v.base_model, v.adapter, v.quantization].filter(Boolean).join(' · ') || 'No version details recorded'}
      actions={v.variant && <Badge tone={variantTone}>{v.variant === 'finetuned' ? 'Fine-tuned' : v.variant}</Badge>}>
      {small && (
        <Alert tone="warning" title="Small sample">
          Based on {plural(v.model_calls, 'model call')} and {plural(v.questions, 'question')}. Rates this small can swing a lot with a few more runs, so treat them as early signals, not conclusions.
        </Alert>
      )}
      <div className="lc-mq__cols">
        <section aria-labelledby={`rel-${v.model_version_id}`}>
          <h3 id={`rel-${v.model_version_id}`} className="lc-h3">Reliability (automatic checks)</h3>
          <div className="lc-rates">
            <Count label="Generation runs" value={v.runs} hint={`${v.runs_failed} failed, ${v.runs_partial} partial`} />
            <Count label="Model calls" value={v.model_calls} hint={`${v.passed_checks} passed the checks for ${v.requested} requested`} />
            <Rate label="Pass rate" value={v.pass_rate} of="Model calls whose output passed every check" />
            <Rate label="Retry rate" value={v.retry_rate} of="Model calls that were rejected and retried" />
            <Rate label="Run failure rate" value={v.run_failure_rate} of={`${v.runs_failed} of ${v.runs} runs produced no usable question`} />
            <Count label="Time per question" value={v.avg_seconds_per_question != null ? duration(v.avg_seconds_per_question) : null} hint="Average across runs" />
          </div>
          <h4 className="lc-mini-label" style={{ marginTop: 'var(--space-4)' }}>Why outputs were rejected</h4>
          {v.rejected_by_check.length === 0 ? <p className="muted lc-small">No output has been rejected by the checks.</p> : (
            <ul className="list-plain lc-reasons">
              {v.rejected_by_check.map((r) => (
                <li key={r.reason}>
                  <div className="row-between lc-small"><span>{r.text}</span><span className="num">{r.count}</span></div>
                  <div className="lc-hbar" aria-hidden="true"><span style={{ width: `${(r.count / maxRej) * 100}%` }} /></div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby={`hum-${v.model_version_id}`}>
          <h3 id={`hum-${v.model_version_id}`} className="lc-h3">Human review (your decisions)</h3>
          <div className="lc-rates">
            <Count label="Generated questions" value={v.questions} hint="Kept in your question bank" />
            <Count label="Approved" value={v.approved} />
            <Count label="Rejected" value={v.rejected} />
            <Count label="Edited before use" value={v.edited} />
            <Count label="Waiting for review" value={v.pending} />
            <Rate label="Approval rate" value={v.approval_rate} of={`${v.approved} of ${reviewed} reviewed questions`} />
            <Rate label="Rejection rate" value={v.rejection_rate} of={`${v.rejected} of ${reviewed} reviewed questions`} />
            <Rate label="Edit rate" value={v.edit_rate} of={`${v.edited} of ${v.questions} questions were edited`} />
          </div>
        </section>
      </div>
    </Card>
  )
}

export default function ModelQuality() {
  const d = useApi(() => lecturerApi.modelQuality(), [])
  return (
    <div className="stack-lg">
      <Alert tone="info" title="What this view measures">
        Reliability comes from your generation runs and the automatic checks; human review comes from what you approved, rejected and edited.
        Whether answers are actually correct, questions are on topic and difficulty labels match are judged by people offline with the evaluation pipeline in <code>backend/evaluation</code>, so they are not shown here.
        Small counts are not conclusive.
      </Alert>
      {d.loading && <LoadingBlock rows={3} label="Loading model quality" />}
      {d.error && <ErrorState error={d.error} onRetry={d.reload} />}
      {d.data && (d.data.versions.length === 0 ? (
        <EmptyState icon={FlaskConical} title="No generated questions yet" action={<Button variant="primary" to="/lecturer/create">Generate a quiz</Button>}>
          Model statistics appear after you generate questions and review them.
        </EmptyState>
      ) : (
        <>
          {d.data.versions.map((v) => <VersionCard key={v.model_version_id ?? 'unknown'} v={v} />)}
          {d.data.note && <p className="faint lc-small">{d.data.note}</p>}
        </>
      ))}
    </div>
  )
}
