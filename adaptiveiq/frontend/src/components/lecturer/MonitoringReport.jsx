import { useMemo, useState } from 'react'
import {
  Camera, CheckCircle2, Clock, Eye, Maximize, Mic, Search, ShieldAlert, ShieldCheck, UploadCloud,
} from 'lucide-react'
import { lecturerApi } from '../../api/endpoints'
import { useApi } from '../../api/useApi'
import {
  Alert, Badge, Button, Card, Dialog, EmptyState, ErrorState, Field, Input, LoadingBlock, Segmented, Stat,
  Textarea, useToast,
} from '../ui'
import { dateTime } from '../../utils/format'
import {
  DEVICE_STATE, REVIEW_TEXT, STATUS_TEXT, STATUS_TONE, eventDetailHint, eventDeviceText, eventLine, eventSource, secs,
} from '../../monitoring/labels'
import { errText } from './util'

const s1 = (x) => `${Math.round(x)} s`

export function StatusBadge({ status }) {
  return <Badge tone={STATUS_TONE[status]}>{STATUS_TEXT[status] || status}</Badge>
}

function inferAvailability(r, st) {
  if (r.signal_availability) return r.signal_availability
  const notMon = r.status === 'not_monitored' || r.monitoring_state === 'not_monitored'
  return {
    tab: notMon || !st?.tab ? 'not_monitored' : 'active',
    fullscreen: notMon || !st?.fullscreen || st.fullscreen === 'off' ? 'not_monitored' : 'active',
    camera: notMon || (!st?.camera && r.camera === 'not_requested') ? 'not_monitored' : (r.camera === 'granted' ? 'active' : 'unavailable'),
    microphone: notMon || (!st?.microphone && r.microphone === 'not_requested') ? 'not_monitored' : (r.microphone === 'granted' ? 'active' : 'unavailable'),
  }
}

function normalizeRow(r, st) {
  const counts = r.counts || {}
  const avail = inferAvailability(r, st)
  const hasRecordedEvents = r.has_recorded_events ?? Boolean(
    counts.tab_switches || counts.fullscreen_exits || counts.no_face || counts.multiple_faces
    || counts.speech || counts.camera_issues || counts.microphone_issues,
  )
  const notMon = r.status === 'not_monitored' || r.monitoring_state === 'not_monitored'
  const monitoringState = r.monitoring_state ?? (
    notMon ? 'not_monitored'
      : r.status === 'unavailable' ? 'unavailable'
        : Object.values(avail).includes('unavailable') ? 'partial' : 'active'
  )
  const awaitingReview = r.awaiting_review ?? (!r.review && (r.status === 'needs_review' || r.status === 'event_recorded' || r.status === 'unavailable'))
  const lastActivityAt = r.last_activity_at || r.last_event_at || null
  const isZeroClean = !hasRecordedEvents && monitoringState === 'active' && r.status === 'normal'
  const isUnavailableOrUnmonitored = monitoringState !== 'active' || r.status === 'unavailable' || r.status === 'not_monitored'
  return { ...r, counts, avail, hasRecordedEvents, monitoringState, awaitingReview, lastActivityAt, isZeroClean, isUnavailableOrUnmonitored }
}

function deviceBadgeText(kind, state, monitored) {
  if (!monitored && state === 'not_requested') return null
  const label = kind === 'camera' ? 'Camera' : 'Mic'
  if (monitored && state === 'not_requested') return `${label}: unavailable`
  if (state === 'denied') return `${label}: not allowed`
  if (state === 'unavailable') return `${label}: not found`
  if (state === 'granted') return `${label}: allowed`
  return `${label}: ${DEVICE_STATE[state] || state}`
}

function SignalCountCell({ count, formatted, availState, subline }) {
  if (count > 0) {
    return (
      <>
        <span className="num">{formatted}</span>
        {availState === 'unavailable' && <span className="faint lc-small lc-block">Device unavailable</span>}
        {subline}
      </>
    )
  }
  if (availState === 'not_monitored') return <span className="faint lc-small">Not monitored</span>
  if (availState === 'unavailable') return <span className="lc-warn lc-small">Unavailable</span>
  return (
    <>
      <span className="num">0</span>
      {subline}
    </>
  )
}

function Timeline({ id, onClose, onSaved }) {
  const { notify } = useToast()
  const { data: t, error, loading, reload, setData } = useApi(() => lecturerApi.monitoringTimeline(id), [id])
  const [note, setNote] = useState(null)
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState(null)
  const save = async (review) => {
    setBusy(review || 'not_reviewed')
    setErr(null)
    try {
      const nextNote = (note ?? t.review_note ?? '') || null
      const r = await lecturerApi.monitoringReview(id, { review, note: nextNote })
      setData({ ...t, ...r })
      setNote(null)
      onSaved?.()
      notify(review ? 'Review saved' : 'Marked as not reviewed')
    } catch (e) {
      setErr(errText(e))
    } finally {
      setBusy(null)
    }
  }
  return (
    <Dialog open onClose={onClose} wide title={t ? `${t.student} · attempt ${t.attempt_no}` : 'Monitoring timeline'}
      description={t ? `${t.quiz_title}. ${t.attempt_status === 'submitted' ? `Submitted ${dateTime(t.submitted_at)}` : 'Attempt in progress'} · Started ${dateTime(t.started_at)}.` : undefined}>
      {loading && !t ? <LoadingBlock rows={4} /> : error ? <ErrorState error={error} onRetry={reload} /> : (
        <div className="stack-lg">
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <StatusBadge status={t.status} />
            <Badge tone={t.review === 'follow_up' ? 'warning' : t.review === 'no_concern' ? 'success' : undefined}>
              {t.review ? (REVIEW_TEXT[t.review] || t.review) : REVIEW_TEXT.none}
            </Badge>
            {t.settings?.camera && <Badge>Camera: {DEVICE_STATE[t.camera] || t.camera}</Badge>}
            {t.settings?.microphone && <Badge>Microphone: {DEVICE_STATE[t.microphone] || t.microphone}</Badge>}
            {t.last_event_at && <span className="faint lc-small">Last activity {dateTime(t.last_event_at)}</span>}
          </div>
          <Alert tone="info">
            Activity events are indicators for manual review, not proof of misconduct. No raw video, audio, or face identity check is used.
          </Alert>
          {t.dropped_events > 0 && (
            <Alert tone="warning">
              {t.dropped_events} browser event(s) could not be stored (outside the attempt time window or over the per-attempt cap).
            </Alert>
          )}
          {t.reasons.length > 0 && <ul className="lc-mon-reasons">{t.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
          {t.warning_count != null && <section aria-label="Student warning history">
            <h3>Activity warnings: {t.warning_count} / {t.warning_threshold}</h3>
            {t.review_required && <p>Warning threshold reached; lecturer review required. Answers and marks are unaffected.</p>}
            <ol>{(t.warning_history || []).map((e) => <li key={e.seq}>{dateTime(e.at)} · {eventLine(e)}</li>)}</ol>
          </section>}
          <div className="stack" style={{ gap: 8 }}>
            <p className="eyebrow">Timeline ({t.timeline.length} recorded events, browser clock)</p>
            {t.timeline.length ? (
              <ol className="lc-mon-timeline">
                {t.timeline.map((e) => {
                  const hint = eventDetailHint(e)
                  const dev = eventDeviceText(e)
                  const uploaded = e.uploaded !== undefined
                    ? Boolean(e.uploaded)
                    : (e.received_at !== undefined ? Boolean(e.received_at) : true)
                  return (
                    <li key={e.seq} data-kind={e.kind} className="lc-mon-event">
                      <span className="faint num" title={dateTime(e.at)}>{new Date(e.at).toLocaleTimeString()}</span>
                      <div className="lc-mon-event__body">
                        <div className="row-between" style={{ gap: 8, flexWrap: 'wrap' }}>
                          <span>{eventLine(e)}</span>
                          <Badge tone={uploaded ? 'success' : 'warning'} icon={UploadCloud}>
                            {uploaded ? 'Uploaded' : 'Pending'}
                          </Badge>
                        </div>
                        <div className="lc-mon-event__meta faint lc-small">
                          {hint && <span>{hint}</span>}
                          <span>Source: {eventSource(e)}</span>
                          {e.duration_ms != null && <span>Duration: {secs(e.duration_ms)}</span>}
                          {dev && <span>Device: {dev}</span>}
                          {e.received_at && <span>Received: {dateTime(e.received_at)}</span>}
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ol>
            ) : (
              <p className="muted lc-small">
                {t.status === 'unavailable'
                  ? 'No events reached the server for this attempt, so monitoring data is unavailable.'
                  : 'No activity events were recorded for this attempt.'}
              </p>
            )}
          </div>
          <div className="stack" style={{ gap: 8 }}>
            <div className="row-between" style={{ flexWrap: 'wrap', gap: 8 }}>
              <span className="field__label">Manual review outcome</span>
              {t.reviewed_at && <span className="faint lc-small">Saved {dateTime(t.reviewed_at)}</span>}
            </div>
            <Field label="Your note (optional, only you see it)">
              {(a) => <Textarea {...a} rows={2} maxLength={1000} value={note ?? t.review_note ?? ''} onChange={(e) => setNote(e.target.value)} />}
            </Field>
            {err && <Alert tone="error">{err}</Alert>}
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <Button size="sm" variant={!t.review ? 'primary' : 'secondary'} aria-pressed={!t.review}
                onClick={() => save(null)} loading={busy === 'not_reviewed'}>Not reviewed</Button>
              <Button size="sm" variant={t.review === 'no_concern' ? 'primary' : 'secondary'} aria-pressed={t.review === 'no_concern'}
                onClick={() => save('no_concern')} loading={busy === 'no_concern'}>Mark: no concern</Button>
              <Button size="sm" variant={t.review === 'follow_up' ? 'primary' : 'secondary'} aria-pressed={t.review === 'follow_up'}
                onClick={() => save('follow_up')} loading={busy === 'follow_up'}>Mark: follow-up needed</Button>
            </div>
          </div>
        </div>
      )}
    </Dialog>
  )
}

export default function MonitoringReport({ quiz, goTo, onChanged }) {
  const { data: d, error, loading, reload } = useApi(() => lecturerApi.quizMonitoring(quiz.id), [quiz.id])
  const [open, setOpen] = useState(null)
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')

  const st = d?.settings || null
  const rows = useMemo(() => (d?.students || []).map((r) => normalizeRow(r, st)), [d, st])

  const countsByGroup = useMemo(() => {
    const withEvents = rows.filter((r) => r.hasRecordedEvents).length
    const noEvents = rows.filter((r) => r.isZeroClean).length
    const awaiting = rows.filter((r) => r.awaitingReview).length
    const unavailable = rows.filter((r) => r.isUnavailableOrUnmonitored).length
    return { total: rows.length, withEvents, noEvents, awaiting, unavailable }
  }, [rows])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows.filter((r) => {
      if (filter === 'with_events' && !r.hasRecordedEvents) return false
      if (filter === 'no_events' && !r.isZeroClean) return false
      if (filter === 'awaiting_review' && !r.awaitingReview) return false
      if (filter === 'unavailable' && !r.isUnavailableOrUnmonitored) return false
      if (q && !(r.student || '').toLowerCase().includes(q) && !(r.email || '').toLowerCase().includes(q)) return false
      return true
    })
  }, [rows, filter, search])

  if (loading && !d) return <LoadingBlock rows={3} label="Loading monitoring" />
  if (error) return <ErrorState error={error} onRetry={reload} title="Could not load monitoring" />

  if (!st && !d.students.length) {
    return (
      <EmptyState icon={ShieldCheck} title="Monitoring is off for this quiz"
        action={goTo && quiz.status === 'draft' ? <Button variant="secondary" onClick={() => goTo('settings')}>Open settings</Button> : null}>
        Turn it on in Settings before students start: page switches, full screen, camera (face count) and microphone (speech-like sound).
        Only events are stored, never video or audio.
      </EmptyState>
    )
  }

  const filterOptions = [
    { value: 'all', label: `All students (${countsByGroup.total})` },
    { value: 'with_events', label: `With recorded events (${countsByGroup.withEvents})` },
    { value: 'no_events', label: `No recorded events (${countsByGroup.noEvents})` },
    { value: 'awaiting_review', label: `Awaiting review (${countsByGroup.awaiting})` },
    { value: 'unavailable', label: `Unavailable / not monitored (${countsByGroup.unavailable})` },
  ]

  return (
    <div className="stack-lg">
      <Card title="Assessment monitoring & activity"
        subtitle={`Activity events are indicators for manual review, not proof of misconduct. Stored events are deleted after ${d.retention_days} days.`}>
        <div className="stack">
          {st ? (
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              {st.tab && <Badge icon={Eye}>Tab & window switches</Badge>}
              {st.fullscreen !== 'off' && <Badge icon={Maximize}>Full screen {st.fullscreen === 'required' ? 'required' : 'recorded'}</Badge>}
              {st.camera && <Badge icon={Camera}>Camera: face presence & count</Badge>}
              {st.microphone && <Badge icon={Mic}>Microphone: speech-like sound</Badge>}
            </div>
          ) : (
            <Alert tone="info">Monitoring is currently off for new attempts on this quiz. Earlier attempts remain listed below.</Alert>
          )}
          <div className="lc-mon-stats">
            <Stat label="Students / attempts" value={countsByGroup.total} icon={ShieldCheck} tone="teal" />
            <Stat label="With recorded events" value={countsByGroup.withEvents} icon={ShieldAlert} tone="accent"
              hint="Tab, face, audio, or device issues" />
            <Stat label="No recorded events" value={countsByGroup.noEvents} icon={CheckCircle2} tone="success"
              hint="Actively monitored, 0 events" />
            <Stat label="Unavailable / not monitored" value={countsByGroup.unavailable} icon={Camera} tone="warning"
              hint="Denied, offline, or unmonitored" />
            <Stat label="Awaiting lecturer review" value={countsByGroup.awaiting} icon={Clock} tone="warning"
              hint="Unreviewed activity or missing device data" />
          </div>
          <p className="lc-small faint">
            Totals: <strong>{d.totals.needs_review}</strong> need review · <strong>{d.totals.event_recorded}</strong> event recorded ·{' '}
            <strong>{d.totals.normal}</strong> normal{d.summary?.unavailable ? ` · ${d.summary.unavailable} unavailable` : ''}
            {d.summary?.not_monitored ? ` · ${d.summary.not_monitored} not monitored` : ''}.
            Zero events indicates active monitoring recorded no issues, whereas missing permissions or disabled monitoring are shown separately as unavailable or not monitored.
          </p>
          <details className="lc-details">
            <summary>When an attempt is marked "Needs review"</summary>
            <ul className="lc-mon-reasons">{d.rules.needs_review_when.map((r) => <li key={r}>{r}</li>)}</ul>
            <p className="muted lc-small">{d.rules.note}</p>
          </details>
        </div>
      </Card>

      {rows.length ? (
        <Card title="Student monitoring summary" subtitle="Sorted with attempts needing review first. Click a student or Timeline to inspect details and record your review.">
          <div className="stack">
            <div className="lc-mon-toolbar">
              <Segmented name="monitoring-filter" label="Filter students by monitoring status" value={filter} onChange={setFilter} options={filterOptions} />
              <div className="lc-search lc-mon-search">
                <Search size={15} aria-hidden="true" />
                <Input type="search" aria-label="Search monitored students" placeholder="Search student or email"
                  value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
            </div>
            {filtered.length ? (
              <div className="table-wrap">
                <table className="table lc-mon-table">
                  <thead>
                    <tr>
                      <th scope="col">Student</th>
                      <th scope="col">Attempt status</th>
                      <th scope="col" className="num">Tab / window leaves</th>
                      <th scope="col" className="num">Face absence</th>
                      <th scope="col" className="num">Multiple faces</th>
                      <th scope="col" className="num">Speech-like audio</th>
                      <th scope="col">Camera / mic status</th>
                      <th scope="col">Last activity</th>
                      <th scope="col">Manual review</th>
                      <th scope="col" />
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((r) => {
                      const camText = deviceBadgeText('camera', r.camera, st?.camera)
                      const micText = deviceBadgeText('microphone', r.microphone, st?.microphone)
                      const fsSubline = (r.avail.fullscreen !== 'not_monitored' && (st?.fullscreen && st.fullscreen !== 'off')) || r.counts.fullscreen_exits > 0
                        ? <span className="faint lc-small lc-block">Fullscreen exits: {r.counts.fullscreen_exits}</span> : null
                      return (
                        <tr key={r.id ?? `sess-${r.session_id}`}>
                          <td>
                            {r.id != null ? (
                              <button type="button" className="lc-mon-student-btn" onClick={() => setOpen(r.id)}>
                                {r.student || `Student #${r.student_id}`}
                              </button>
                            ) : (
                              <strong>{r.student || `Student #${r.student_id}`}</strong>
                            )}
                            <span className="faint lc-small lc-block lc-mon-student-meta" title={r.email || undefined}>
                              attempt {r.attempt_no}{r.email ? ` · ${r.email}` : ''}
                            </span>
                          </td>
                          <td>
                            <div className="stack" style={{ gap: 4, justifyItems: 'start' }}>
                              <Badge tone={r.attempt_status === 'submitted' ? 'teal' : 'accent'}>
                                {r.attempt_status === 'submitted' ? 'Submitted' : 'In progress'}
                              </Badge>
                              <StatusBadge status={r.status} />
                            </div>
                          </td>
                          <td className="num">
                            <SignalCountCell
                              count={r.counts.tab_switches}
                              formatted={`${r.counts.tab_switches} · ${s1(r.counts.hidden_s)}`}
                              availState={r.avail.tab}
                              subline={fsSubline}
                            />
                          </td>
                          <td className="num">
                            <SignalCountCell
                              count={r.counts.no_face}
                              formatted={`${r.counts.no_face} · ${s1(r.counts.no_face_s)}`}
                              availState={r.avail.camera}
                            />
                          </td>
                          <td className="num">
                            <SignalCountCell
                              count={r.counts.multiple_faces}
                              formatted={r.counts.multiple_faces}
                              availState={r.avail.camera}
                            />
                          </td>
                          <td className="num">
                            <SignalCountCell
                              count={r.counts.speech}
                              formatted={`${r.counts.speech}${r.counts.speech_prolonged ? ` (${r.counts.speech_prolonged} long)` : ''} · ${secs(r.counts.speech_s * 1000)}`}
                              availState={r.avail.microphone}
                            />
                          </td>
                          <td className="lc-small">
                            {r.monitoringState === 'not_monitored' ? (
                              <span className="faint">Not monitored</span>
                            ) : (
                              <div className="stack" style={{ gap: 2 }}>
                                {camText && <span className={r.camera === 'denied' || r.camera === 'unavailable' || (st?.camera && r.camera === 'not_requested') ? 'lc-warn' : 'muted'}>{camText}</span>}
                                {micText && <span className={r.microphone === 'denied' || r.microphone === 'unavailable' || (st?.microphone && r.microphone === 'not_requested') ? 'lc-warn' : 'muted'}>{micText}</span>}
                                {!camText && !micText && <span className="faint">Not required</span>}
                              </div>
                            )}
                          </td>
                          <td className="lc-small">
                            {r.lastActivityAt ? dateTime(r.lastActivityAt) : (
                              <span className="faint">{r.monitoringState === 'active' ? 'No events' : '—'}</span>
                            )}
                          </td>
                          <td>
                            {r.status === 'not_monitored' && r.id == null ? (
                              <span className="faint lc-small">Not monitored</span>
                            ) : r.review ? (
                              <>
                                <Badge tone={r.review === 'follow_up' ? 'warning' : 'success'}>
                                  {REVIEW_TEXT[r.review] || r.review}
                                </Badge>
                                {r.review_note && <span className="faint lc-small lc-block lc-mon-note">{r.review_note}</span>}
                              </>
                            ) : (
                              <span className={r.awaitingReview ? 'lc-warn lc-small' : 'faint lc-small'}>
                                {REVIEW_TEXT.none}
                              </span>
                            )}
                          </td>
                          <td>
                            {r.id != null ? (
                              <Button size="sm" variant="ghost" onClick={() => setOpen(r.id)}
                                aria-label={`Timeline for ${r.student}, attempt ${r.attempt_no}`}>Timeline</Button>
                            ) : (
                              <span className="faint lc-small">No record</span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="lc-three row-between" style={{ flexWrap: 'wrap', gap: 12 }}>
                <span className="muted lc-small">No student attempts match the current filter.</span>
                <Button size="sm" variant="secondary" onClick={() => { setFilter('all'); setSearch('') }}>Show all students</Button>
              </div>
            )}
          </div>
        </Card>
      ) : (
        <EmptyState icon={ShieldCheck} title="No student attempts yet">Attempts appear here once students start the quiz.</EmptyState>
      )}
      {open && <Timeline key={open} id={open} onClose={() => setOpen(null)} onSaved={() => { reload(); onChanged?.() }} />}
    </div>
  )
}
