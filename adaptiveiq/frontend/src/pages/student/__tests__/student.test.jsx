import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../../components/ui'
import { attemptAssessment, attemptPractice, checkResponse, resultBody, run, topic } from './fixtures'

vi.mock('../../../api/endpoints', () => ({
  studentApi: {
    attempt: vi.fn(), saveAnswer: vi.fn(), checkAnswer: vi.fn(), submit: vi.fn(), result: vi.fn(), mastery: vi.fn(), quiz: vi.fn(),
    start: vi.fn(), practiceQuizzes: vi.fn(), recommendedDifficulty: vi.fn(), generatePractice: vi.fn(), confidence: vi.fn(),
  },
  topicsApi: { choices: vi.fn() },
  generationApi: { get: vi.fn(), cancel: vi.fn() },
  healthApi: { get: vi.fn() },
  authApi: {},
}))

const { studentApi, topicsApi, generationApi, healthApi } = await import('../../../api/endpoints')
const { default: QuizPlayer } = await import('../QuizPlayer')
const { default: Result } = await import('../Result')
const { default: Practice, RUN_KEY } = await import('../Practice')
const { default: TopicMasteryCard } = await import('../../../components/student/TopicMasteryCard')

function renderAt(path, routePath, el) {
  return render(
    <ToastProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={routePath} element={el} />
          <Route path="/student/attempts/:sessionId/result" element={<p>RESULT PAGE</p>} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  window.sessionStorage.clear()
})

describe('QuizPlayer', () => {
  it('autosaves a choice with the time spent and shows the saved state', async () => {
    studentApi.attempt.mockResolvedValue(attemptAssessment)
    studentApi.saveAnswer.mockResolvedValue({ option_id: 10, confidence: null, checked: false, time_spent_s: 1 })
    renderAt('/student/attempts/1', '/student/attempts/:sessionId', <QuizPlayer />)
    expect(await screen.findByText('Which scheduler is non-preemptive by default?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('radio', { name: /Option beta 5/ }))
    await waitFor(() => expect(studentApi.saveAnswer).toHaveBeenCalledWith('1', '3', expect.objectContaining({ option_id: 10, confidence: null })))
    expect(typeof studentApi.saveAnswer.mock.calls[0][2].time_spent_s).toBe('number')
    expect(await screen.findByText('All answers saved')).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /Option beta 5/ })).toHaveAttribute('aria-checked', 'true')
  })

  it('restores saved answers, supports keyboard choice and lists unanswered questions before submit', async () => {
    studentApi.attempt.mockResolvedValue({ ...attemptAssessment, answers: { 3: { option_id: 10, confidence: null, checked: false, time_spent_s: 12 } } })
    studentApi.saveAnswer.mockResolvedValue({})
    studentApi.submit.mockResolvedValue(resultBody)
    renderAt('/student/attempts/1', '/student/attempts/:sessionId', <QuizPlayer />)
    // resumes at the first unanswered question
    expect(await screen.findByText('Which algorithm suits time-sharing systems?')).toBeInTheDocument()
    expect(screen.getByText('1/3 answered')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'c' })
    await waitFor(() => expect(studentApi.saveAnswer).toHaveBeenCalledWith('1', '5', expect.objectContaining({ option_id: 19 })))
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(screen.getByText('Which queue structure suits multilevel feedback?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Submit quiz' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('1 question unanswered')).toBeInTheDocument()
    expect(within(dialog).getByText(/Questions: 3\./)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Submit now' }))
    expect(await screen.findByText('RESULT PAGE')).toBeInTheDocument()
    expect(studentApi.submit).toHaveBeenCalledWith('1')
  })

  it('goes to the result when the server says time is up', async () => {
    const { ApiError } = await import('../../../api/client')
    studentApi.attempt.mockResolvedValue(attemptAssessment)
    studentApi.saveAnswer.mockRejectedValue(new ApiError(409, 'Time is up. Your saved answers were submitted.'))
    renderAt('/student/attempts/1', '/student/attempts/:sessionId', <QuizPlayer />)
    fireEvent.click(await screen.findByRole('radio', { name: /Option beta 5/ }))
    expect(await screen.findByText('RESULT PAGE')).toBeInTheDocument()
  })

  it('practice mode: Check reveals the key and locks the answer', async () => {
    studentApi.attempt.mockResolvedValue(attemptPractice)
    studentApi.saveAnswer.mockResolvedValue({})
    studentApi.checkAnswer.mockResolvedValue(checkResponse)
    renderAt('/student/attempts/2', '/student/attempts/:sessionId', <QuizPlayer />)
    fireEvent.click(await screen.findByRole('radio', { name: /Option gamma 5/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Sure' }))
    await waitFor(() => expect(studentApi.saveAnswer).toHaveBeenLastCalledWith('2', '3', expect.objectContaining({ option_id: 11, confidence: 3 })))
    fireEvent.click(screen.getByRole('button', { name: /Check answer/ }))
    expect(await screen.findByText(/Not quite. The answer is B/)).toBeInTheDocument()
    expect(screen.getByText('Beta 5 is correct because of reason 5.')).toBeInTheDocument()
    const calls = studentApi.saveAnswer.mock.calls.length
    fireEvent.click(screen.getByRole('radio', { name: /Option alpha 5/ }))
    await act(async () => { await new Promise((r) => setTimeout(r, 20)) })
    expect(studentApi.saveAnswer.mock.calls.length).toBe(calls)
  })
})

describe('Result', () => {
  it('keeps raw score, percentage, final and grade contribution as separate labelled numbers', async () => {
    studentApi.result.mockResolvedValue(resultBody)
    studentApi.mastery.mockResolvedValue({ topics: [topic], method: null })
    renderAt('/student/attempts/1/result', '/student/attempts/:sessionId/result', <Result />)
    expect(await screen.findByText('Raw score')).toBeInTheDocument()
    expect(screen.getByText('Percentage')).toBeInTheDocument()
    expect(screen.getByText('40.0%')).toBeInTheDocument()
    expect(screen.getByText('Final after late penalty')).toBeInTheDocument()
    expect(screen.getByText('30.0%')).toBeInTheDocument()
    expect(screen.getByText('Contribution to the subject grade')).toBeInTheDocument()
    expect(screen.getByText(/10% penalty applied/)).toBeInTheDocument()
    // skipped kept apart from incorrect
    expect(screen.getAllByText('Skipped').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Incorrect').length).toBeGreaterThan(0)
    expect(await screen.findByText('45')).toBeInTheDocument()
    expect(screen.getByText('Beta 5 is correct because of reason 5.')).toBeInTheDocument()
  })

  it('explains when feedback is withheld', async () => {
    studentApi.result.mockResolvedValue({ session_id: 1, quiz_id: 1, quiz_title: 'Scheduling quiz 1', kind: 'assessment', attempt_no: 1,
      submitted_at: '2026-10-21T16:43:23Z', submitted_by: 'student', is_late: false, feedback_available: false,
      feedback_message: 'Your answers are submitted. Your lecturer will release results later.', percentage: null, items: [], topics: [], recommendations: [], can_retry: false })
    studentApi.mastery.mockResolvedValue({ topics: [] })
    studentApi.quiz.mockResolvedValue({ id: 1, due_at: null })
    renderAt('/student/attempts/1/result', '/student/attempts/:sessionId/result', <Result />)
    expect(await screen.findByText(/Your lecturer will release results later/)).toBeInTheDocument()
    expect(screen.queryByText('Raw score')).not.toBeInTheDocument()
  })
})

describe('TopicMasteryCard', () => {
  it('shows score, evidence, trend and next step', () => {
    render(<MemoryRouter><TopicMasteryCard topic={topic} /></MemoryRouter>)
    expect(screen.getByLabelText('Estimated mastery 45 out of 100')).toBeInTheDocument()
    expect(screen.getByText('5 questions answered: 2 correct, 2 wrong, 1 skipped')).toBeInTheDocument()
    expect(screen.getByText('Not enough data for a trend')).toBeInTheDocument()
    expect(screen.getByText(topic.next_action_text)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Practise CPU Scheduling' })).toHaveAttribute('href', expect.stringContaining('topic_id=1'))
  })

  it('does not present a score as fact with insufficient evidence', () => {
    render(<MemoryRouter><TopicMasteryCard topic={{ ...topic, label: 'insufficient_evidence', unique_questions: 2, answers: 2, correct: 1, incorrect: 1, skipped: 0, evidence_level: 'low', evidence_text: 'Insufficient evidence' }} /></MemoryRouter>)
    expect(screen.getByText('Insufficient evidence for an estimate')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Estimated mastery/)).not.toBeInTheDocument()
  })
})

describe('Practice', () => {
  beforeEach(() => {
    healthApi.get.mockResolvedValue({ model: { state: 'ok' } })
    studentApi.practiceQuizzes.mockResolvedValue([])
    topicsApi.choices.mockResolvedValue([{ topic_id: 1, topic: 'CPU Scheduling', unit_id: 1, unit: 'Unit 2: Scheduling', subject_id: 1, subject: 'Operating Systems', course_id: 1, course: 'Operating Systems', objectives: [] }])
    studentApi.recommendedDifficulty.mockResolvedValue({ difficulty: 'easy', reason: 'Estimated mastery 45% is below 50%, so difficulty goes down one level to rebuild the basics.' })
  })

  it('shows the recommended difficulty with its reason and sends a course topic', async () => {
    studentApi.generatePractice.mockResolvedValue({ ...run, status: 'queued', difficulty_note: 'note' })
    generationApi.get.mockResolvedValue(run)
    renderAt('/student/practice', '/student/practice', <Practice />)
    expect(await screen.findByText(/so difficulty goes down one level/, {}, { timeout: 2000 })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Generate practice quiz/ }))
    await waitFor(() => expect(studentApi.generatePractice).toHaveBeenCalledWith(expect.objectContaining({ topic_id: 1, difficulty: 'adaptive', question_count: 5 })))
    expect(JSON.parse(window.sessionStorage.getItem(RUN_KEY)).runId).toBe(2)
    expect(await screen.findByText(/2 of 5 questions passed the checks/)).toBeInTheDocument()
  })

  it('keeps showing a stored run after a refresh', async () => {
    window.sessionStorage.setItem(RUN_KEY, JSON.stringify({ runId: 2, quizId: 2, topic: 'SQL joins', note: null }))
    generationApi.get.mockResolvedValue({ ...run, status: 'done', ready: 5, stage: 'Questions ready' })
    renderAt('/student/practice', '/student/practice', <Practice />)
    expect(await screen.findByText('Ready: SQL joins')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Start the quiz \(5 questions\)/ })).toBeInTheDocument()
  })
})
