import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  BookmarkPlus,
  BookOpen,
  CalendarDays,
  CheckCircle2,
  Clock,
  Compass,
  Eye,
  FlaskConical,
  GitBranch,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from 'lucide-react'
import { Alert, Badge, Button, Card, EmptyState, ErrorState, LoadingBlock, ProgressBar } from '../ui'
import { studentApi } from '../../api/endpoints'
import { DIFFICULTY_TEXT, STATUS_TEXT, dateTime, plural } from '../../utils/format'

const KIND_META = {
  prerequisite: { label: 'Prerequisite first', tone: 'warning' },
  revisit_incorrect: { label: 'Due revision', tone: 'teal' },
  practice_topic: { label: 'Focus topic', tone: 'accent' },
  gather_evidence: { label: 'Gather evidence', tone: undefined },
  diagnostic_start: { label: 'Start topic', tone: undefined },
  upcoming_assessment: { label: 'Assessment', tone: 'accent' },
  try_harder: { label: 'Step up', tone: 'success' },
  maintain: { label: 'Maintain', tone: 'success' },
}

const STATUS_TONE = {
  weak: 'error',
  developing: 'warning',
  ok: 'success',
  insufficient_evidence: undefined,
  not_attempted: undefined,
  upcoming_assessment: 'accent',
}

const PLAN_STATUS_META = {
  proposed: { label: 'Proposed', tone: undefined },
  awaiting_approval: { label: 'Awaiting approval', tone: 'accent' },
  in_progress: { label: 'In progress', tone: 'teal' },
  completed: { label: 'Completed', tone: 'success' },
  dismissed: { label: 'Dismissed', tone: undefined },
  expired: { label: 'Expired', tone: 'warning' },
  failed: { label: 'Attention needed', tone: 'error' },
}

const ITEM_STATUS_META = {
  in_progress: { label: 'In progress', tone: 'accent', icon: PlayCircle },
  completed: { label: 'Completed', tone: 'success', icon: CheckCircle2 },
  postponed: { label: 'Postponed', tone: 'warning', icon: PauseCircle },
  dismissed: { label: 'Dismissed', tone: undefined, icon: X },
  superseded: { label: 'Replaced on refresh', tone: undefined, icon: undefined },
}

function newIdemKey(plan, item) {
  const rand = typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID().slice(0, 12)
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
  return `${plan.id}-${item.activity_id}-g${plan.generation_seq || 1}-${rand}`
}

function actionIcon(actionType) {
  switch (actionType) {
    case 'navigate_revision':
    case 'start_revision':
      return RotateCcw
    case 'open_profile':
      return SlidersHorizontal
    case 'open_courses':
      return BookOpen
    case 'open_quiz':
    case 'open_assessment':
      return CalendarDays
    case 'prefill_practice':
    case 'practice_lab':
    case 'start_practice':
    default:
      return FlaskConical
  }
}

function approveButtonLabel(item) {
  const actType = item.approved_action_type || item.next_action?.action_type
  if (actType === 'start_revision') return 'Start Due Revision'
  if (actType === 'open_assessment') return 'Open Assigned Assessment'
  return 'Start Recommended Practice'
}

function actionHumanSummary(item) {
  const actType = item.approved_action_type || item.next_action?.action_type
  if (actType === 'start_revision') {
    return item.due_revision_count
      ? `Start Due Revision (${plural(item.due_revision_count, 'due question')})`
      : 'Start Due Revision'
  }
  if (actType === 'open_assessment') {
    return item.next_action?.label || 'Open Assigned Assessment'
  }
  const diff = (DIFFICULTY_TEXT[item.recommended_difficulty] || item.recommended_difficulty || 'Mixed').toLowerCase()
  return `Start ${diff} practice`
}

function ActionButton({ action, variant = 'secondary', size = 'sm' }) {
  if (!action) return null
  const Icon = actionIcon(action.action_type)
  if (action.action_type === 'navigate_revision' || action.target_href === '/student/insights#revision') {
    return (
      <Button
        size={size}
        variant={variant === 'secondary' ? 'teal' : variant}
        icon={Icon}
        href="#revision"
        onClick={() => document.getElementById('revision')?.scrollIntoView({ block: 'start' })}
      >
        {action.label}
      </Button>
    )
  }
  return (
    <Button size={size} variant={variant} icon={Icon} to={action.target_href}>
      {action.label}
    </Button>
  )
}

function evidenceMeta(item) {
  if (item.evidence_sufficient && item.mastery_score_pct != null) {
    return `Mastery ${item.mastery_score_pct}% · ${plural(item.unique_questions, 'question')}`
  }
  if (item.unique_questions > 0) {
    return `Tentative (${item.unique_questions}/${item.min_evidence} questions for mastery)`
  }
  return `No attempts yet (min ${item.min_evidence} questions)`
}

export default function LearningPlan() {
  const navigate = useNavigate()
  const [persistentPlan, setPersistentPlan] = useState(null)
  const [previewPlan, setPreviewPlan] = useState(null)
  const [showPreviewOnly, setShowPreviewOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [actionNotice, setActionNotice] = useState(null)
  const [busyKey, setBusyKey] = useState(null)
  const inFlightRef = useRef(false)
  const idemKeysRef = useRef({})

  const loadInitial = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const hasCurrent = typeof studentApi.learningPlanCurrent === 'function'
      const cur = hasCurrent ? await studentApi.learningPlanCurrent() : null
      if (cur && (cur.stage === 2 || cur.id != null)) {
        setPersistentPlan(cur)
        setPreviewPlan(null)
        setShowPreviewOnly(false)
      } else {
        setPersistentPlan(null)
        const prev = await studentApi.learningPlanPreview()
        setPreviewPlan(prev)
        setShowPreviewOnly(false)
      }
    } catch (err) {
      setError(err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadInitial()
  }, [loadInitial])

  const isPersistentView = Boolean(persistentPlan && !showPreviewOnly)
  const data = isPersistentView ? persistentPlan : (previewPlan || persistentPlan)
  const summary = data?.summary

  const runAction = async (key, fn) => {
    if (inFlightRef.current) return
    inFlightRef.current = true
    setBusyKey(key)
    setActionError(null)
    setActionNotice(null)
    try {
      await fn()
    } catch (err) {
      setActionError(err)
    } finally {
      inFlightRef.current = false
      setBusyKey(null)
    }
  }

  const handleSavePlan = () => runAction('create', async () => {
    const created = await studentApi.learningPlanCreate({})
    setPersistentPlan(created)
    setShowPreviewOnly(false)
    setActionNotice('Learning plan saved. Review and approve any step when you are ready.')
  })

  const handleRefreshPlan = () => {
    if (!persistentPlan) {
      loadInitial()
      return
    }
    return runAction('refresh', async () => {
      const updated = await studentApi.learningPlanRefresh(persistentPlan.id, {})
      idemKeysRef.current = {}
      setPersistentPlan(updated)
      setShowPreviewOnly(false)
      setActionNotice('Plan refreshed using your latest mastery, prerequisite, and revision data.')
    })
  }

  const handleDismissPlan = () => {
    if (!persistentPlan) return
    return runAction('dismiss_plan', async () => {
      const updated = await studentApi.learningPlanDismiss(persistentPlan.id, { scope: 'plan' })
      setPersistentPlan(updated)
      setActionNotice('Learning plan dismissed. Your quiz marks and mastery history were not changed.')
    })
  }

  const handleApproveItem = (item) => {
    if (!persistentPlan) return
    const cacheKey = `${persistentPlan.id}:${persistentPlan.generation_seq}:${item.activity_id}`
    if (!idemKeysRef.current[cacheKey]) {
      idemKeysRef.current[cacheKey] = newIdemKey(persistentPlan, item)
    }
    const idempotency_key = idemKeysRef.current[cacheKey]
    return runAction(`approve:${item.activity_id}`, async () => {
      const updated = await studentApi.learningPlanApprove(persistentPlan.id, {
        activity_id: item.activity_id,
        idempotency_key,
      })
      delete idemKeysRef.current[cacheKey]
      setPersistentPlan(updated)
      const exec = updated.last_execution
      if (exec?.message) {
        setActionNotice(exec.message)
      }
      if (exec?.destination_href && exec.destination_href.startsWith('/student/')) {
        navigate(exec.destination_href)
      }
    })
  }

  const handlePostponeItem = (item) => {
    if (!persistentPlan) return
    return runAction(`postpone:${item.activity_id}`, async () => {
      const updated = await studentApi.learningPlanPostpone(persistentPlan.id, {
        activity_id: item.activity_id,
        scope: 'item',
        postpone_days: 2,
      })
      setPersistentPlan(updated)
      setActionNotice(`Postponed ${item.topic} for 2 days.`)
    })
  }

  const handleDismissItem = (item) => {
    if (!persistentPlan) return
    return runAction(`dismiss:${item.activity_id}`, async () => {
      const updated = await studentApi.learningPlanDismiss(persistentPlan.id, {
        activity_id: item.activity_id,
        scope: 'item',
      })
      setPersistentPlan(updated)
      setActionNotice(`Dismissed recommendation for ${item.topic}.`)
    })
  }

  const handleTogglePreview = async () => {
    if (showPreviewOnly) {
      setShowPreviewOnly(false)
      return
    }
    if (!previewPlan) {
      await runAction('preview', async () => {
        const prev = await studentApi.learningPlanPreview()
        setPreviewPlan(prev)
        setShowPreviewOnly(true)
      })
    } else {
      setShowPreviewOnly(true)
    }
  }

  const planClosed = Boolean(
    persistentPlan && ['completed', 'dismissed', 'expired', 'failed'].includes(persistentPlan.status),
  )
  const canCreateNew = Boolean(!persistentPlan || planClosed)
  const progress = isPersistentView ? data?.progress : null
  const activeCount = progress ? Math.max(0, (progress.total_items || 0) - (progress.dismissed_items || 0)) : 0
  const planMeta = data?.status ? (PLAN_STATUS_META[data.status] || { label: data.status, tone: undefined }) : null

  const headerActions = (
    <div className="st-agent__head-actions">
      {isPersistentView ? (
        <>
          <Badge tone="teal">Current Plan</Badge>
          {planMeta && <Badge tone={planMeta.tone}>{planMeta.label}</Badge>}
        </>
      ) : (
        <Badge tone="teal">Read-only preview</Badge>
      )}
      {summary?.budget_status === 'allocated' && (
        <Badge tone="accent" icon={Clock}>
          {summary.weekly_study_hours} h/week · {summary.allocated_minutes} min
        </Badge>
      )}
      {summary?.budget_status === 'zero_hours' && (
        <Badge tone="warning" icon={Clock}>0 h/week configured</Badge>
      )}
      {summary?.budget_status === 'unconfigured' && (
        <Badge icon={Clock}>Weekly hours not set · ~{summary.allocated_hours} h suggested</Badge>
      )}
      {isPersistentView ? (
        <>
          <Button
            size="sm"
            variant="ghost"
            icon={RefreshCw}
            onClick={handleRefreshPlan}
            loading={busyKey === 'refresh'}
            disabled={!!busyKey || loading}
          >
            Refresh Plan
          </Button>
          {!planClosed && (
            <Button
              size="sm"
              variant="ghost"
              icon={X}
              onClick={handleDismissPlan}
              loading={busyKey === 'dismiss_plan'}
              disabled={!!busyKey || loading}
            >
              Dismiss Plan
            </Button>
          )}
          {canCreateNew && typeof studentApi.learningPlanCreate === 'function' && (
            <Button
              size="sm"
              variant="primary"
              icon={BookmarkPlus}
              onClick={handleSavePlan}
              loading={busyKey === 'create'}
              disabled={!!busyKey || loading}
            >
              Save &amp; Start Learning Plan
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            icon={Eye}
            onClick={handleTogglePreview}
            loading={busyKey === 'preview'}
            disabled={!!busyKey || loading}
          >
            Preview
          </Button>
        </>
      ) : (
        <>
          <Button size="sm" variant="ghost" icon={RefreshCw} onClick={loadInitial} loading={loading} disabled={!!busyKey}>
            Refresh
          </Button>
          {persistentPlan && showPreviewOnly && (
            <Button size="sm" variant="secondary" onClick={() => setShowPreviewOnly(false)} disabled={!!busyKey}>
              Current Plan
            </Button>
          )}
          {canCreateNew && typeof studentApi.learningPlanCreate === 'function' && (
            <Button
              size="sm"
              variant="primary"
              icon={BookmarkPlus}
              onClick={handleSavePlan}
              loading={busyKey === 'create'}
              disabled={!!busyKey || loading}
            >
              Save &amp; Start Learning Plan
            </Button>
          )}
        </>
      )}
    </div>
  )

  const helperActions = isPersistentView
    ? (data?.proposed_next_actions || []).filter((a) => ['open_profile', 'open_courses', 'practice_lab'].includes(a.action_type))
    : (data?.proposed_next_actions || [])

  return (
    <Card
      className="st-agent"
      title="Personalized Learning Plan"
      subtitle={summary?.headline || 'Prioritized study plan built from your mastery, prerequisite links, and due spaced revision.'}
      actions={headerActions}
    >
      {loading && !data ? (
        <LoadingBlock rows={3} />
      ) : error ? (
        <ErrorState error={error} onRetry={loadInitial} />
      ) : (
        <div className="stack">
          <p className="st-small muted">{summary.rationale}</p>

          {actionError && (
            <Alert tone="error" title="Action could not be completed">
              {actionError.message}
            </Alert>
          )}

          {actionNotice && (
            <Alert tone="success" title="Plan updated">
              {actionNotice}
            </Alert>
          )}

          {isPersistentView && progress && progress.total_items > 0 && (
            <div className="st-agent__progress" aria-label="Learning plan progress">
              <div className="st-agent__progress-head">
                <span className="st-small">
                  <strong>{progress.completed_items}</strong> of <strong>{activeCount || progress.total_items}</strong>{' '}
                  {activeCount === 1 ? 'activity' : 'activities'} completed
                  {progress.in_progress_items > 0 ? ` · ${progress.in_progress_items} in progress` : ''}
                  {progress.postponed_items > 0 ? ` · ${progress.postponed_items} postponed` : ''}
                  {data.generation_seq > 1 ? ` · Revision ${data.generation_seq}` : ''}
                </span>
                <span className="st-small num muted">{progress.completion_pct}%</span>
              </div>
              <ProgressBar
                value={progress.completed_items}
                max={activeCount || 1}
                label="Learning plan progress"
                tone={data.status === 'completed' ? 'success' : undefined}
              />
            </div>
          )}

          {isPersistentView && data.pending_approval?.awaiting_approval && (
            <Alert tone="info" title="Pending Approval">
              <div className="st-agent__approval-copy">
                <ShieldCheck size={15} aria-hidden="true" className="st-inline-icon" />
                <span>{data.pending_approval.prompt} No quiz or practice generation starts until you approve a step below.</span>
              </div>
            </Alert>
          )}

          {data.warnings?.length > 0 && (
            <Alert tone="warning" title="Plan notes">
              <ul className="st-agent__warnings">
                {data.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </Alert>
          )}

          {data.items?.length > 0 ? (
            <ol className="st-plan st-agent__list" aria-label="Personalized study sessions">
              {data.items.map((item) => {
                const km = KIND_META[item.kind] || { label: item.kind, tone: undefined }
                const sTone = STATUS_TONE[item.status]
                const zeroBudget = summary.budget_status === 'zero_hours'
                const itemMeta = isPersistentView ? ITEM_STATUS_META[item.item_status] : null
                const actType = item.approved_action_type || item.next_action?.action_type

                return (
                  <li key={item.id ?? item.activity_id} className="appear">
                    <span className="st-plan__n num" aria-hidden="true">{item.rank}</span>
                    <div className="st-plan__main">
                      <div className="row" style={{ gap: 8 }}>
                        <strong>{item.topic}</strong>
                        <span className="faint st-small">{item.subject}</span>
                        <Badge tone={km.tone}>{km.label}</Badge>
                        <Badge tone={sTone}>{STATUS_TEXT[item.status] || item.status}</Badge>
                        {itemMeta && (
                          <Badge tone={itemMeta.tone} icon={itemMeta.icon}>
                            {itemMeta.label}
                          </Badge>
                        )}
                        {isPersistentView && item.is_refreshed_new && (
                          <Badge tone={item.change_status === 'new' ? 'teal' : 'accent'}>
                            {item.change_status === 'new' ? 'New after refresh' : 'Updated'}
                          </Badge>
                        )}
                      </div>
                      <p className="st-small">{item.reason}</p>
                      <p className="faint st-small">
                        {DIFFICULTY_TEXT[item.recommended_difficulty] || item.recommended_difficulty} difficulty
                        {' · '}
                        {evidenceMeta(item)}
                        {item.due_revision_count > 0 ? ` · ${plural(item.due_revision_count, 'due question')}` : ''}
                        {item.prerequisite_of?.length > 0 ? ` · Prerequisite for ${item.prerequisite_of.join(', ')}` : ''}
                        {item.blocked_by_prerequisite ? ` · Practise after ${item.blocked_by_prerequisite}` : ''}
                        {isPersistentView ? ` · Action: ${actionHumanSummary(item)}` : ''}
                        {item.postponed_until && item.item_status === 'postponed'
                          ? ` · Postponed until ${dateTime(item.postponed_until)}`
                          : ''}
                      </p>
                    </div>
                    <div className="st-plan__side st-agent__item-side">
                      <span className={`num st-plan__hours${zeroBudget ? ' muted' : ''}`}>
                        {zeroBudget
                          ? '0 min'
                          : `${item.estimated_minutes} min${item.estimated_hours ? ` · ${item.estimated_hours} h` : ''}`}
                      </span>
                      {isPersistentView ? (
                        <div className="st-agent__item-controls">
                          {item.can_approve && (
                            <Button
                              size="sm"
                              variant={actType === 'start_revision' ? 'teal' : 'primary'}
                              icon={actionIcon(actType)}
                              onClick={() => handleApproveItem(item)}
                              loading={busyKey === `approve:${item.activity_id}`}
                              disabled={!!busyKey}
                            >
                              {approveButtonLabel(item)}
                            </Button>
                          )}
                          {item.item_status === 'in_progress' && item.execution_ref?.destination_href && (
                            <Button
                              size="sm"
                              variant="teal"
                              icon={actionIcon(actType)}
                              to={item.execution_ref.destination_href}
                            >
                              Continue activity
                            </Button>
                          )}
                          {item.can_postpone && (
                            <Button
                              size="sm"
                              variant="ghost"
                              icon={PauseCircle}
                              onClick={() => handlePostponeItem(item)}
                              loading={busyKey === `postpone:${item.activity_id}`}
                              disabled={!!busyKey}
                            >
                              Postpone
                            </Button>
                          )}
                          {item.can_dismiss && (
                            <Button
                              size="sm"
                              variant="ghost"
                              icon={X}
                              onClick={() => handleDismissItem(item)}
                              loading={busyKey === `dismiss:${item.activity_id}`}
                              disabled={!!busyKey}
                            >
                              Dismiss
                            </Button>
                          )}
                        </div>
                      ) : (
                        <ActionButton
                          action={item.next_action}
                          variant={item.kind === 'revisit_incorrect' ? 'teal' : 'ghost'}
                        />
                      )}
                    </div>
                  </li>
                )
              })}
            </ol>
          ) : (
            <EmptyState icon={Compass} title="No eligible study material yet">
              {summary.empty_reason || 'Join a course or generate a practice quiz when you are ready to begin.'}
            </EmptyState>
          )}

          {data.deferred_topics?.length > 0 && (
            <p className="faint st-small">
              Deferred for now: {data.deferred_topics.map((d) => d.topic).join(', ')}.
            </p>
          )}

          {isPersistentView && data.previous_items?.length > 0 && (
            <details className="st-agent__trace">
              <summary>
                <Clock size={13} aria-hidden="true" /> Previous recommendations ({data.previous_items.length})
              </summary>
              <div className="st-agent__trace-body">
                <ul className="st-agent__edges">
                  {data.previous_items.map((prev) => {
                    const m = ITEM_STATUS_META[prev.item_status] || { label: prev.item_status }
                    return (
                      <li key={`prev-${prev.id}-${prev.activity_id}`} className="st-small muted">
                        <strong>Epoch {prev.revision_epoch} · {prev.topic}</strong> ({prev.subject}) — {m.label}
                        {prev.completed_at ? ` (${dateTime(prev.completed_at)})` : ''}
                      </li>
                    )
                  })}
                </ul>
              </div>
            </details>
          )}

          {helperActions.length > 0 && (
            <div className="st-agent__actions" aria-label="Proposed next actions">
              <div className="st-agent__actions-head">
                <span className="eyebrow">
                  <ArrowRight size={13} aria-hidden="true" /> Proposed next actions
                </span>
                <span className="faint st-small">
                  {isPersistentView
                    ? 'Optional profile & course shortcuts — recommended study actions require your explicit approval above.'
                    : 'Preview only — no changes are saved automatically.'}
                </span>
              </div>
              <div className="row">
                {helperActions.map((act, idx) => (
                  <ActionButton
                    key={`${act.action_type}:${act.target_href}`}
                    action={act}
                    variant={idx === 0 ? 'primary' : 'secondary'}
                  />
                ))}
              </div>
            </div>
          )}

          {data.graph_trace?.nodes_visited?.length > 0 && (
            <details className="st-agent__trace">
              <summary>
                <GitBranch size={13} aria-hidden="true" /> How this plan was routed ({data.routing_mode})
              </summary>
              <div className="st-agent__trace-body">
                <p className="st-small faint">
                  Graph nodes: {data.graph_trace.nodes_visited.join(' → ')} · Stage {data.stage} deterministic policy ({data.graph_version}).
                </p>
                {data.graph_trace.edges_taken?.length > 0 && (
                  <ul className="st-agent__edges">
                    {data.graph_trace.edges_taken.map((edge, idx) => (
                      <li key={`${edge.from_node}-${edge.to_node}-${idx}`} className="st-small muted">
                        <code>{edge.from_node}</code> —[{edge.condition}]→ <code>{edge.to_node}</code>: {edge.reason}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </details>
          )}
        </div>
      )}
    </Card>
  )
}
