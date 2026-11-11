// Phase 6: integrity monitoring screens: consent on the quiz page, the gate and recorded events in the player,
// a denied camera, the lecturer's report with neutral labels, and the settings form.
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../ui'
import { attemptAssessment } from '../../../pages/student/__tests__/fixtures'

vi.mock('../../../api/endpoints', () => ({
  studentApi: {
    quiz: vi.fn(), start: vi.fn(), attempt: vi.fn(), saveAnswer: vi.fn(), submit: vi.fn(), checkAnswer: vi.fn(),
    myMonitoring: vi.fn(), monitoringEvents: vi.fn(), monitoringDevices: vi.fn(),
  },
  lecturerApi: { quizMonitoring: vi.fn(), monitoringTimeline: vi.fn(), monitoringReview: vi.fn() },
  topicsApi: {}, generationApi: {}, healthApi: {}, authApi: {},
}))
const { studentApi, lecturerApi } = await import('../../../api/endpoints')
const { default: QuizIntro } = await import('../../../pages/student/QuizIntro')
const { default: QuizPlayer } = await import('../../../pages/student/QuizPlayer')
const { default: MonitoringReport } = await import('../../lecturer/MonitoringReport')
const { toBody } = await import('../../lecturer/QuizSettingsForm')

const WATCH = { tab: true, fullscreen: 'off', camera: false, microphone: false }
const card = {
  id: 1, title: 'Scheduling quiz 1', kind: 'assessment', course_title: 'OS', subject: 'OS', topics: ['CPU Scheduling'], lecturer: 'Dr L',
  question_count: 3, max_marks: 3, time_limit_min: null, opens_at: null, due_at: null, closes_at: null, attempts_allowed: 1,
  attempts_used: 0, state: 'open', in_progress_session_id: null, last_session_id: null, best_percentage: null, graded: true,
  contribution_pct: 5, created_at: '2026-11-01T10:00:00Z', monitoring: { ...WATCH, camera: true, microphone: true },
}

function at(path, route, el) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={el} />
          <Route path="/student/attempts/:sessionId" element={<p>PLAYER</p>} />
          <Route path="/student/attempts/:sessionId/result" element={<p>RESULT PAGE</p>} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  )
}

let vis = 'visible'
beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  vis = 'visible'
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => vis })
  studentApi.myMonitoring.mockResolvedValue({ events: [] })
  studentApi.monitoringEvents.mockResolvedValue({ stored: 1 })
  studentApi.monitoringDevices.mockResolvedValue({})
})
afterEach(() => { delete navigator.mediaDevices })

const setVisible = (v) => act(() => { vis = v; document.dispatchEvent(new Event('visibilitychange')) })
const sentKinds = () => studentApi.monitoringEvents.mock.calls.flatMap((c) => c[1].map((e) => e.kind))

describe('Quiz page consent', () => {
  it('explains what is recorded and only starts after the student agrees', async () => {
    studentApi.quiz.mockResolvedValue(card)
    studentApi.start.mockResolvedValue({ session_id: 9 })
    at('/student/quizzes/1', '/student/quizzes/:quizId', <QuizIntro />)
    expect(await screen.findByText('This assessment is monitored')).toBeInTheDocument()
    expect(screen.getByText(/No picture or video is saved or sent/)).toBeInTheDocument()
    expect(screen.getByText(/No audio is recorded, saved or sent/)).toBeInTheDocument()
    expect(screen.getByText(/contact your lecturer about another way/)).toBeInTheDocument()
    const startBtn = screen.getByRole('button', { name: /start/i })
    expect(startBtn).toBeDisabled()
    fireEvent.click(screen.getByLabelText(/I have read what is recorded and agree/))
    fireEvent.click(startBtn)
    await waitFor(() => expect(studentApi.start).toHaveBeenCalledWith(1, { monitoring_consent: true }))
    expect(await screen.findByText('PLAYER')).toBeInTheDocument()
  })
  it('asks nothing for a quiz without monitoring', async () => {
    studentApi.quiz.mockResolvedValue({ ...card, monitoring: null })
    studentApi.start.mockResolvedValue({ session_id: 9 })
    at('/student/quizzes/1', '/student/quizzes/:quizId', <QuizIntro />)
    fireEvent.click(await screen.findByRole('button', { name: /start/i }))
    await waitFor(() => expect(studentApi.start).toHaveBeenCalledWith(1, {}))
    expect(screen.queryByText('This assessment is monitored')).not.toBeInTheDocument()
  })
})

describe('Monitored quiz player', () => {
  const monitored = (m) => ({ ...attemptAssessment, monitoring: { ...m, camera_state: 'not_requested', microphone_state: 'not_requested', face_interval_ms: 1500, retention_days: 180 } })

  it('shows the gate first, then records leaving the page and tells the student', async () => {
    studentApi.attempt.mockResolvedValue(monitored(WATCH))
    at('/student/attempts/1', '/student/attempts/:sessionId', <QuizPlayer />)
    expect(await screen.findByText('This assessment is monitored')).toBeInTheDocument()
    expect(screen.queryByText('Which scheduler is non-preemptive by default?')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Turn on monitoring and continue' }))
    expect(await screen.findByText('Which scheduler is non-preemptive by default?')).toBeInTheDocument()
    expect(screen.getByText('Monitored')).toBeInTheDocument()
    await waitFor(() => expect(studentApi.monitoringDevices).toHaveBeenCalledWith('1', { camera: 'not_requested', microphone: 'not_requested' }))
    setVisible('hidden')
    setVisible('visible')
    expect(await screen.findByText(/You left the quiz page for 1 second\. This was recorded/)).toBeInTheDocument()
    setVisible('hidden')                                            // leaving again sends what is waiting
    await waitFor(() => expect(sentKinds()).toEqual(expect.arrayContaining(['monitoring_started', 'page_hidden', 'page_visible'])))
    const visible = studentApi.monitoringEvents.mock.calls.flatMap((c) => c[1]).find((e) => e.kind === 'page_visible')
    expect(typeof visible.duration_ms).toBe('number')
  })

  it('continues the sequence numbers the server already has after a reload', async () => {
    studentApi.attempt.mockResolvedValue(monitored(WATCH))
    studentApi.myMonitoring.mockResolvedValue({ events: [{ seq: 4 }, { seq: 7 }] })
    at('/student/attempts/1', '/student/attempts/:sessionId', <QuizPlayer />)
    fireEvent.click(await screen.findByRole('button', { name: 'Turn on monitoring and continue' }))
    await waitFor(() => expect(studentApi.monitoringEvents).toHaveBeenCalled())
    expect(studentApi.monitoringEvents.mock.calls[0][1][0].seq).toBe(8)
  })

  it('lets the student continue when the camera is not allowed, and records that', async () => {
    navigator.mediaDevices = { getUserMedia: vi.fn().mockRejectedValue(Object.assign(new Error('no'), { name: 'NotAllowedError' })) }
    studentApi.attempt.mockResolvedValue(monitored({ ...WATCH, camera: true }))
    at('/student/attempts/1', '/student/attempts/:sessionId', <QuizPlayer />)
    fireEvent.click(await screen.findByRole('button', { name: 'Turn on monitoring and continue' }))
    expect(await screen.findByText('Which scheduler is non-preemptive by default?')).toBeInTheDocument()
    expect(screen.getByText('Camera not allowed')).toBeInTheDocument()
    await waitFor(() => expect(studentApi.monitoringDevices).toHaveBeenCalledWith('1', { camera: 'denied', microphone: 'not_requested' }))
    await waitFor(() => expect(sentKinds()).toContain('camera_denied'))
  })

  it('sends the remaining events when the quiz is submitted', async () => {
    studentApi.attempt.mockResolvedValue(monitored(WATCH))
    studentApi.submit.mockResolvedValue({})
    at('/student/attempts/1', '/student/attempts/:sessionId', <QuizPlayer />)
    fireEvent.click(await screen.findByRole('button', { name: 'Turn on monitoring and continue' }))
    await screen.findByText('Which scheduler is non-preemptive by default?')
    await waitFor(() => expect(studentApi.monitoringEvents).toHaveBeenCalled())
    studentApi.monitoringEvents.mockClear()
    setVisible('hidden')
    studentApi.monitoringEvents.mockRejectedValueOnce(Object.assign(new Error('offline'), { status: 0 }))
    setVisible('visible')
    fireEvent.click(screen.getByRole('button', { name: 'Submit quiz' }))
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Submit now' }))
    expect(await screen.findByText('RESULT PAGE')).toBeInTheDocument()
    await waitFor(() => expect(sentKinds()).toContain('page_visible'))
  })
})

describe('Lecturer monitoring report', () => {
  const report = {
    quiz_id: 1, quiz_title: 'Scheduling quiz 1', settings: { tab: true, fullscreen: 'required', camera: true, microphone: true },
    rules: { algorithm: 'monitor-rules-v1', needs_review_when: ['the quiz page is hidden 3 or more times'], note: 'These are signals for you to review, not proof of anything.' },
    retention_days: 180, totals: { needs_review: 1, event_recorded: 0, normal: 1 },
    students: [
      { id: 5, session_id: 11, student_id: 3, student: 'Student Two', email: 's2@example.edu', attempt_no: 1, attempt_status: 'submitted',
        started_at: '2026-11-02T10:00:00Z', submitted_at: '2026-11-02T10:20:00Z', camera: 'granted', microphone: 'denied', status: 'needs_review',
        reasons: ['The quiz page was hidden 3 times.'], counts: { tab_switches: 3, hidden_s: 75, fullscreen_exits: 0, no_face: 1, no_face_s: 4,
          multiple_faces: 0, multiple_faces_s: 0, speech: 1, speech_s: 12, speech_prolonged: 1, camera_issues: 0, microphone_issues: 1 },
        events: 8, review: null, review_note: null, reviewed_at: null },
      { id: 4, session_id: 10, student_id: 2, student: 'Student One', email: 's1@example.edu', attempt_no: 1, attempt_status: 'submitted',
        started_at: '2026-11-02T10:00:00Z', submitted_at: '2026-11-02T10:20:00Z', camera: 'granted', microphone: 'granted', status: 'normal',
        reasons: [], counts: { tab_switches: 0, hidden_s: 0, fullscreen_exits: 0, no_face: 0, no_face_s: 0, multiple_faces: 0, multiple_faces_s: 0,
          speech: 0, speech_s: 0, speech_prolonged: 0, camera_issues: 0, microphone_issues: 0 }, events: 1, review: null, review_note: null, reviewed_at: null },
    ],
  }
  it('shows neutral statuses with counts, the timeline and a review', async () => {
    lecturerApi.quizMonitoring.mockResolvedValue(report)
    lecturerApi.monitoringTimeline.mockResolvedValue({ ...report.students[0], quiz_id: 1, quiz_title: 'Scheduling quiz 1', settings: report.settings,
      consented_at: '2026-11-02T10:00:00Z', dropped_events: 0,
      timeline: [{ seq: 1, kind: 'page_hidden', at: '2026-11-02T10:01:00Z', duration_ms: null, details: {} },
        { seq: 2, kind: 'page_visible', at: '2026-11-02T10:01:25Z', duration_ms: 25000, details: {} },
        { seq: 3, kind: 'speech', at: '2026-11-02T10:05:00Z', duration_ms: 12000, details: {} }] })
    lecturerApi.monitoringReview.mockResolvedValue({ review: 'no_concern', review_note: 'Told me about a call.', reviewed_at: '2026-11-02T11:00:00Z' })
    const { container } = at('/x', '/x', <MonitoringReport quiz={{ id: 1, status: 'published' }} />)
    const row = (await screen.findByText('Student Two')).closest('tr')
    expect(within(row).getByText('Needs review')).toBeInTheDocument()
    expect(within(row).getByText('3 · 75 s')).toBeInTheDocument()
    expect(within(row).getByText('1 (1 long) · 12 s')).toBeInTheDocument()
    expect(within(screen.getByText('Student One').closest('tr')).getByText('Normal')).toBeInTheDocument()
    expect(container.textContent.toLowerCase()).not.toMatch(/cheat|suspicious|guilty/)
    fireEvent.click(within(row).getByRole('button', { name: /Timeline for Student Two/ }))
    const dlg = await screen.findByRole('dialog')
    expect(await within(dlg).findByText('Came back to the quiz page (away 25 s)')).toBeInTheDocument()
    expect(within(dlg).getByText('Speech-like sound (for 12 s)')).toBeInTheDocument()
    fireEvent.change(within(dlg).getByLabelText(/Your note/), { target: { value: 'Told me about a call.' } })
    fireEvent.click(within(dlg).getByRole('button', { name: 'Mark: no concern' }))
    await waitFor(() => expect(lecturerApi.monitoringReview).toHaveBeenCalledWith(5, { review: 'no_concern', note: 'Told me about a call.' }))
    expect(await within(dlg).findByText('Reviewed: no concern')).toBeInTheDocument()
  })
  it('explains how to turn monitoring on when it is off', async () => {
    lecturerApi.quizMonitoring.mockResolvedValue({ ...report, settings: null, students: [], totals: { needs_review: 0, event_recorded: 0, normal: 0 } })
    at('/x', '/x', <MonitoringReport quiz={{ id: 1, status: 'draft' }} goTo={() => {}} />)
    expect(await screen.findByText('Monitoring is off for this quiz')).toBeInTheDocument()
  })

  it('distinguishes active zero events from unavailable or unmonitored data, filters accurately, and supports all 3 review states', async () => {
    const fiveReport = {
      quiz_id: 2, quiz_title: 'Operating Systems Midterm', quiz_status: 'archived',
      settings: { tab: true, fullscreen: 'record', camera: true, microphone: true },
      rules: report.rules, retention_days: 180,
      totals: { needs_review: 1, event_recorded: 2, normal: 1 },
      students: [
        { id: 11, session_id: 101, student_id: 21, student: 'Student A Tabs', email: 'a@example.edu', attempt_no: 1, attempt_status: 'submitted',
          started_at: '2026-11-02T10:00:00Z', submitted_at: '2026-11-02T10:20:00Z', camera: 'granted', microphone: 'granted',
          status: 'event_recorded', reasons: ['Some events were recorded.'],
          counts: { tab_switches: 2, hidden_s: 15, fullscreen_exits: 0, no_face: 0, no_face_s: 0, multiple_faces: 0, multiple_faces_s: 0, speech: 0, speech_s: 0, speech_prolonged: 0, camera_issues: 0, microphone_issues: 0 },
          events: 4, last_event_at: '2026-11-02T10:05:00Z', awaiting_review: true, review: null, review_note: null, reviewed_at: null },
        { id: 12, session_id: 102, student_id: 22, student: 'Student B Face', email: 'b@example.edu', attempt_no: 1, attempt_status: 'submitted',
          started_at: '2026-11-02T10:00:00Z', submitted_at: '2026-11-02T10:20:00Z', camera: 'granted', microphone: 'granted',
          status: 'needs_review', reasons: ['More than one face was detected 1 time.'],
          counts: { tab_switches: 0, hidden_s: 0, fullscreen_exits: 1, no_face: 2, no_face_s: 8, multiple_faces: 1, multiple_faces_s: 2, speech: 0, speech_s: 0, speech_prolonged: 0, camera_issues: 0, microphone_issues: 0 },
          events: 4, last_event_at: '2026-11-02T10:08:00Z', awaiting_review: true, review: 'follow_up', review_note: 'Verify workspace', reviewed_at: '2026-11-02T11:00:00Z' },
        { id: 13, session_id: 103, student_id: 23, student: 'Student C Audio', email: 'c@example.edu', attempt_no: 1, attempt_status: 'in_progress',
          started_at: '2026-11-02T10:00:00Z', submitted_at: null, camera: 'granted', microphone: 'granted',
          status: 'event_recorded', reasons: ['Some events were recorded.'],
          counts: { tab_switches: 0, hidden_s: 0, fullscreen_exits: 0, no_face: 0, no_face_s: 0, multiple_faces: 0, multiple_faces_s: 0, speech: 1, speech_s: 6, speech_prolonged: 0, camera_issues: 0, microphone_issues: 0 },
          events: 2, last_event_at: '2026-11-02T10:12:00Z', awaiting_review: true, review: null, review_note: null, reviewed_at: null },
        { id: 14, session_id: 104, student_id: 24, student: 'Student D Clean', email: 'd@example.edu', attempt_no: 1, attempt_status: 'submitted',
          started_at: '2026-11-02T10:00:00Z', submitted_at: '2026-11-02T10:20:00Z', camera: 'granted', microphone: 'granted',
          status: 'normal', reasons: [],
          counts: { tab_switches: 0, hidden_s: 0, fullscreen_exits: 0, no_face: 0, no_face_s: 0, multiple_faces: 0, multiple_faces_s: 0, speech: 0, speech_s: 0, speech_prolonged: 0, camera_issues: 0, microphone_issues: 0 },
          events: 1, last_event_at: '2026-11-02T10:00:01Z', awaiting_review: false, monitoring_state: 'active', review: null, review_note: null, reviewed_at: null },
        { id: 15, session_id: 105, student_id: 25, student: 'Student E Unavailable', email: 'e@example.edu', attempt_no: 1, attempt_status: 'submitted',
          started_at: '2026-11-02T10:00:00Z', submitted_at: '2026-11-02T10:20:00Z', camera: 'not_requested', microphone: 'not_requested',
          status: 'unavailable', monitoring_state: 'unavailable', has_recorded_events: false,
          signal_availability: { tab: 'unavailable', fullscreen: 'unavailable', camera: 'unavailable', microphone: 'unavailable' },
          reasons: ['No monitoring telemetry was received.'],
          counts: { tab_switches: 0, hidden_s: 0, fullscreen_exits: 0, no_face: 0, no_face_s: 0, multiple_faces: 0, multiple_faces_s: 0, speech: 0, speech_s: 0, speech_prolonged: 0, camera_issues: 0, microphone_issues: 0 },
          events: 0, last_event_at: null, awaiting_review: true, review: null, review_note: null, reviewed_at: null },
        { id: null, session_id: 106, student_id: 26, student: 'Student F Unmonitored', email: 'f@example.edu', attempt_no: 1, attempt_status: 'submitted',
          started_at: '2026-11-02T09:00:00Z', submitted_at: '2026-11-02T09:20:00Z', camera: 'not_requested', microphone: 'not_requested',
          status: 'not_monitored', monitoring_state: 'not_monitored', has_recorded_events: false,
          signal_availability: { tab: 'not_monitored', fullscreen: 'not_monitored', camera: 'not_monitored', microphone: 'not_monitored' },
          reasons: ['Monitoring was not enabled when this attempt started.'],
          counts: { tab_switches: 0, hidden_s: 0, fullscreen_exits: 0, no_face: 0, no_face_s: 0, multiple_faces: 0, multiple_faces_s: 0, speech: 0, speech_s: 0, speech_prolonged: 0, camera_issues: 0, microphone_issues: 0 },
          events: 0, last_event_at: null, awaiting_review: false, review: null, review_note: null, reviewed_at: null },
      ],
    }
    lecturerApi.quizMonitoring.mockResolvedValue(fiveReport)
    lecturerApi.monitoringTimeline.mockResolvedValue({
      ...fiveReport.students[0], quiz_id: 2, quiz_title: 'Operating Systems Midterm', settings: fiveReport.settings,
      consented_at: '2026-11-02T10:00:00Z', dropped_events: 0,
      timeline: [
        { seq: 1, kind: 'monitoring_started', at: '2026-11-02T10:00:01Z', received_at: '2026-11-02T10:00:02Z', uploaded: true, source: 'Monitoring setup', device_state: { camera: 'granted', microphone: 'granted' }, details: { camera: 'granted', microphone: 'granted' } },
        { seq: 2, kind: 'page_hidden', at: '2026-11-02T10:04:00Z', received_at: '2026-11-02T10:04:02Z', uploaded: true, source: 'Window focus monitor', details: { reason: 'window_blur' } },
        { seq: 3, kind: 'page_visible', at: '2026-11-02T10:04:15Z', received_at: '2026-11-02T10:04:16Z', uploaded: true, duration_ms: 15000, source: 'Window focus monitor', details: { reason: 'window_blur' } },
      ],
    })
    lecturerApi.monitoringReview.mockResolvedValue({ review: null, review_status: 'not_reviewed', review_note: 'Preserved note', reviewed_at: null })

    at('/x', '/x', <MonitoringReport quiz={{ id: 2, status: 'archived' }} />)
    const rowE = (await screen.findByText('Student E Unavailable')).closest('tr')
    expect(within(rowE).getByText('Monitoring unavailable')).toBeInTheDocument()
    expect(within(rowE).getAllByText('Unavailable').length).toBeGreaterThanOrEqual(4)
    expect(within(rowE).queryByText('Normal')).not.toBeInTheDocument()

    const rowF = screen.getByText('Student F Unmonitored').closest('tr')
    expect(within(rowF).getAllByText('Not monitored').length).toBeGreaterThanOrEqual(5)

    // Filter: No recorded events -> only Student D Clean
    fireEvent.click(screen.getByRole('radio', { name: /No recorded events \(1\)/ }))
    expect(screen.getByText('Student D Clean')).toBeInTheDocument()
    expect(screen.queryByText('Student E Unavailable')).not.toBeInTheDocument()

    // Filter: Unavailable / not monitored -> E & F
    fireEvent.click(screen.getByRole('radio', { name: /Unavailable \/ not monitored \(2\)/ }))
    expect(screen.getByText('Student E Unavailable')).toBeInTheDocument()
    expect(screen.getByText('Student F Unmonitored')).toBeInTheDocument()
    expect(screen.queryByText('Student D Clean')).not.toBeInTheDocument()

    // Filter: All students -> open Student A timeline & verify neutral source/upload/duration metadata and 3 review outcomes
    fireEvent.click(screen.getByRole('radio', { name: /All students \(6\)/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Student A Tabs' }))
    const dlg = await screen.findByRole('dialog')
    expect(await within(dlg).findByText('Quiz window lost focus')).toBeInTheDocument()
    expect(within(dlg).getAllByText(/Source: Window focus monitor/).length).toBe(2)
    expect(within(dlg).getByText(/Duration: 15 s/)).toBeInTheDocument()
    expect(within(dlg).getAllByText('Uploaded').length).toBeGreaterThanOrEqual(3)

    fireEvent.change(within(dlg).getByLabelText(/Your note/), { target: { value: 'Preserved note' } })
    fireEvent.click(within(dlg).getByRole('button', { name: 'Not reviewed' }))
    await waitFor(() => expect(lecturerApi.monitoringReview).toHaveBeenCalledWith(11, { review: null, note: 'Preserved note' }))
    expect(within(dlg).getByLabelText(/Your note/)).toHaveValue('Preserved note')
    lecturerApi.monitoringReview.mockResolvedValueOnce({ review: 'follow_up', review_status: 'follow_up', review_note: 'Preserved note', reviewed_at: '2026-11-02T12:00:00Z' })
    fireEvent.click(within(dlg).getByRole('button', { name: 'Mark: follow-up needed' }))
    expect(await within(dlg).findByText('Reviewed — follow-up needed')).toBeInTheDocument()
  })
})

describe('Quiz settings', () => {
  it('sends the monitoring settings', () => {
    const v = { title: 'Q', instructions: '', graded: true, attempts_allowed: '1', time_limit_min: '', opens_at: '', due_at: '', closes_at: '',
      late_policy: 'none', late_penalty_pct: '0', shuffle_questions: false, shuffle_options: false, feedback_release: 'immediate',
      contribution_pct: '5', confidence_enabled: false, target_duration_min: '', monitor_tab: true, monitor_fullscreen: 'required',
      monitor_camera: true, monitor_microphone: false }
    expect(toBody(v)).toMatchObject({ monitor_tab: true, monitor_fullscreen: 'required', monitor_camera: true, monitor_microphone: false })
  })
})
