import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor, within } from '@testing-library/react'
import modelQuality from '../../../../../docs/api-samples/lecturer_model_quality.json'
import heatmap from '../../../../../docs/api-samples/lecturer_heatmap.json'
import heatCell from '../../../../../docs/api-samples/lecturer_heatmap_cell.json'
import quizDetail from '../../../../../docs/api-samples/lecturer_quiz_detail.json'
import quizUpdate from '../../../../../docs/api-samples/lecturer_quiz_update.json'
import preview from '../../../../../docs/api-samples/lecturer_quiz_preview.json'
import runRunning from '../../../../../docs/api-samples/generation_status_running.json'
import publish422 from '../../../../../docs/api-samples/lecturer_publish_unreviewed_422.json'
import { renderAt } from './helpers'

vi.mock('../../../api/endpoints', () => ({
  lecturerApi: {
    modelQuality: vi.fn(), heatmapCell: vi.fn(), quiz: vi.fn(), quizzes: vi.fn(), preview: vi.fn(), publish: vi.fn(), courses: vi.fn(),
    course: vi.fn(), updateItems: vi.fn(), regenerate: vi.fn(), googleStatus: vi.fn(), googleExports: vi.fn(),
    quizMonitoring: vi.fn(), monitoringTimeline: vi.fn(), monitoringReview: vi.fn(), generate: vi.fn(),
  },
  topicsApi: { choices: vi.fn(() => Promise.resolve([])) },
  documentsApi: { extract: vi.fn(), remove: vi.fn(() => Promise.resolve()) },
  generationApi: { get: vi.fn(), cancel: vi.fn() },
  healthApi: { get: vi.fn(() => Promise.resolve({ model: { state: 'ok' } })) },
  authApi: { changePassword: vi.fn(), updateMe: vi.fn(), resendVerification: vi.fn() },
}))
vi.mock('../../../auth/AuthProvider', () => ({
  useAuth: () => ({ user: { full_name: 'Sample Lecturer', email: 'l@example.edu', email_verified: true, created_at: '2026-10-21T00:00:00Z' }, setUser: vi.fn() }),
}))

const { lecturerApi, generationApi, authApi, documentsApi } = await import('../../../api/endpoints')
const { ApiError } = await import('../../../api/client')

beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear() })

describe('Model evaluation view', () => {
  it('shows reliability and human-review rates per model version, with the offline-evaluation and small-sample notes', async () => {
    lecturerApi.modelQuality.mockResolvedValue(modelQuality.body)
    const { default: ModelQuality } = await import('../../../components/lecturer/ModelQuality')
    renderAt(<ModelQuality />)
    expect(await screen.findByText('qwen7b-mcq')).toBeInTheDocument()
    expect(screen.getByText('Pass rate').nextSibling).toHaveTextContent('56%')
    expect(screen.getByText('Retry rate').nextSibling).toHaveTextContent('44%')
    expect(screen.getByText('Approval rate').nextSibling).toHaveTextContent('100%')
    expect(screen.getByText('Edit rate').nextSibling).toHaveTextContent('20%')
    expect(screen.getByText('Python check found a different correct option')).toBeInTheDocument()
    expect(screen.getByText(/backend\/evaluation/)).toBeInTheDocument()
    expect(screen.getByText('Small sample')).toBeInTheDocument()
  })

  it('shows an empty state when nothing was generated', async () => {
    lecturerApi.modelQuality.mockResolvedValue({ versions: [], note: '' })
    const { default: ModelQuality } = await import('../../../components/lecturer/ModelQuality')
    renderAt(<ModelQuality />)
    expect(await screen.findByText('No generated questions yet')).toBeInTheDocument()
  })
})

describe('Mastery heatmap', () => {
  it('distinguishes not attempted from scored cells and opens the cell detail', async () => {
    lecturerApi.heatmapCell.mockResolvedValue(heatCell.body)
    const { default: Heatmap } = await import('../../../components/lecturer/Heatmap')
    renderAt(<Heatmap data={heatmap.body} courseId="1" />)
    // the expected number comes from the fixture, so regenerating docs/api-samples cannot break the test
    const shown = String(Math.round(heatmap.body.students[0].cells[0].score * 100))
    const scored = screen.getByRole('button', { name: new RegExp(`CPU Scheduling: Needs improvement, estimated ${shown} out of 100`) })
    expect(scored).toHaveTextContent(shown)
    const none = screen.getByRole('button', { name: /Round Robin: not attempted/ })
    expect(none).toHaveTextContent('–')
    fireEvent.click(scored)
    expect(await screen.findByText('Suggested intervention')).toBeInTheDocument()
    expect(lecturerApi.heatmapCell).toHaveBeenCalledWith('1', 2, 1)
    expect(screen.getByText('Skipped (counted separately)').nextSibling).toHaveTextContent('1')
  })

  it('filters students by search', async () => {
    const { default: Heatmap } = await import('../../../components/lecturer/Heatmap')
    renderAt(<Heatmap data={heatmap.body} courseId="1" />)
    fireEvent.change(screen.getByLabelText('Search students'), { target: { value: 'zzz' } })
    expect(screen.getByText('No students match these filters.')).toBeInTheDocument()
  })
})

describe('Quiz publishing', () => {
  it('keeps Publish disabled until every question is approved', async () => {
    lecturerApi.quiz.mockResolvedValue(quizDetail.body)
    lecturerApi.preview.mockResolvedValue(preview.body)
    const { default: QuizDetail } = await import('../QuizDetail')
    renderAt(<QuizDetail />, { path: '/lecturer/quizzes/:quizId', route: '/lecturer/quizzes/1?step=publish' })
    const btn = await screen.findByRole('button', { name: 'Publish to students' })
    expect(btn).toBeDisabled()
    expect(screen.getByText('0 of 5 questions approved')).toBeInTheDocument()
  })

  it('shows the API publish validation error (422 detail)', async () => {
    lecturerApi.quiz.mockResolvedValue(quizUpdate.body)
    lecturerApi.preview.mockResolvedValue(preview.body)
    lecturerApi.publish.mockRejectedValue(new ApiError(422, publish422.body.detail, publish422.body))
    const { default: QuizDetail } = await import('../QuizDetail')
    renderAt(<QuizDetail />, { path: '/lecturer/quizzes/:quizId', route: '/lecturer/quizzes/1?step=publish' })
    fireEvent.click(await screen.findByRole('button', { name: 'Publish to students' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish' }))
    expect(await screen.findByText('The quiz was not published')).toBeInTheDocument()
    expect(screen.getAllByText(publish422.body.detail).length).toBeGreaterThan(0)
  })

  it('shows review controls for draft questions', async () => {
    lecturerApi.quiz.mockResolvedValue(quizDetail.body)
    const { default: QuizDetail } = await import('../QuizDetail')
    renderAt(<QuizDetail />, { path: '/lecturer/quizzes/:quizId', route: '/lecturer/quizzes/1' })
    const q1 = await screen.findByRole('article', { name: 'Question 1' })
    expect(within(q1).getByRole('button', { name: 'Approve' })).toBeInTheDocument()
    expect(within(q1).getByRole('button', { name: 'Regenerate' })).toBeInTheDocument()
    expect(within(q1).getByText('Correct answer')).toBeInTheDocument()
  })
})

describe('Create quiz', () => {
  it('restores a running generation from sessionStorage after a refresh', async () => {
    sessionStorage.setItem('aiq.lecturer.generation', JSON.stringify({ runId: 1, quizId: 1, title: 'Scheduling quiz 1', topic: 'CPU Scheduling' }))
    lecturerApi.courses.mockResolvedValue([])
    generationApi.get.mockResolvedValue(runRunning.body)
    const { default: CreateQuiz } = await import('../CreateQuiz')
    renderAt(<CreateQuiz />)
    expect(await screen.findByText('Planning subtopics')).toBeInTheDocument()
    expect(screen.getByText(/Generating “Scheduling quiz 1”/)).toBeInTheDocument()
    expect(generationApi.get).toHaveBeenCalledWith(1)
  })

  it('switches to Upload File mode, extracts a document and submits document generation', async () => {
    lecturerApi.courses.mockResolvedValue([{ id: 1, code: 'CS301', title: 'Operating Systems' }])
    lecturerApi.course.mockResolvedValue({
      id: 1,
      code: 'CS301',
      title: 'Operating Systems',
      subjects: [{
        id: 10,
        name: 'Operating Systems',
        units: [{ id: 100, name: 'Unit 2', topics: [{ id: 1000, name: 'CPU Scheduling', objectives: [] }] }],
      }],
    })
    documentsApi.extract.mockResolvedValue({
      document_id: 'doc-42',
      filename: 'chapter2.pdf',
      file_type: 'pdf',
      size_bytes: 20480,
      page_count: 3,
      word_count: 600,
      chunk_count: 4,
      sections: ['Round Robin', 'Priority Aging'],
      headings: ['Round Robin', 'Priority Aging'],
      recommended_max_questions: 15,
      warning: null,
      preview: 'Round robin scheduling...',
    })
    lecturerApi.generate.mockResolvedValue({ run_id: 99, quiz_id: 55 })
    generationApi.get.mockResolvedValue({
      ...runRunning.body,
      run_id: 99,
      quiz_id: 55,
      grounded_on: 'document',
      document_name: 'chapter2.pdf',
      insufficient_content_note: 'Generated 5 instead of 10 due to short material.',
    })
    const { default: CreateQuiz } = await import('../CreateQuiz')
    renderAt(<CreateQuiz />)
    fireEvent.change(await screen.findByLabelText('Quiz title'), { target: { value: 'Doc Grounded Quiz' } })
    fireEvent.click(screen.getByRole('radio', { name: 'Upload File' }))
    const fileInput = screen.getByLabelText(/Study material file/i)
    const pdfFile = new File(['%PDF-1.4 content'], 'chapter2.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [pdfFile] } })
    expect(await screen.findByText('chapter2.pdf')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/Chapter or section/i), { target: { value: 'Priority Aging' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generate questions' }))
    await waitFor(() => expect(lecturerApi.generate).toHaveBeenCalledWith(expect.objectContaining({
      source_mode: 'document',
      document_id: 'doc-42',
      document_section: 'Priority Aging',
    })))
    expect(await screen.findByText(/From uploaded document \(chapter2\.pdf\)/)).toBeInTheDocument()
    expect(screen.getByText(/Generated 5 instead of 10/)).toBeInTheDocument()
  })
})

describe('Settings', () => {
  it('applies the registration password rules before calling the API', async () => {
    lecturerApi.googleStatus.mockResolvedValue({ configured: false, connected: false, tested_against_google: false, message: 'Not set up.' })
    const { default: Settings } = await import('../Settings')
    renderAt(<Settings />)
    fireEvent.change(screen.getByLabelText('Current password'), { target: { value: 'Passw0rd1' } })
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'short' } })
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'short' } })
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByText('Use at least 8 characters.')).toBeInTheDocument()
    expect(authApi.changePassword).not.toHaveBeenCalled()
    expect(await screen.findByText('Not connected')).toBeInTheDocument()
  })
})

describe('Question editor', () => {
  it('requires four different options and a correct answer', async () => {
    const onSubmit = vi.fn()
    const { default: QuestionEditor } = await import('../../../components/lecturer/QuestionEditor')
    renderAt(<QuestionEditor onSubmit={onSubmit} />)
    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'What does Round Robin do on expiry?' } })
    ;['A', 'B', 'C', 'D'].forEach((l) => fireEvent.change(screen.getByLabelText(`Option ${l}`), { target: { value: 'Same' } }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('The four options must be different.')).toBeInTheDocument()
    ;['A', 'B', 'C', 'D'].forEach((l, i) => fireEvent.change(screen.getByLabelText(`Option ${l}`), { target: { value: `Choice ${i}` } }))
    fireEvent.click(screen.getByLabelText('Option B is correct'))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ correct_label: 'B', options: ['Choice 0', 'Choice 1', 'Choice 2', 'Choice 3'] })
  })
})

describe('Monitoring discoverability', () => {
  it('shows monitoring links on the Quizzes table and quiz summary banner on QuizDetail', async () => {
    const monitoredQuiz = {
      ...quizUpdate.body,
      status: 'published',
      monitor_tab: true,
      monitor_camera: true,
      monitoring_summary: {
        enabled: true, attempt_count: 3, monitored_count: 3, with_events: 2, needs_review: 1, unavailable_count: 0, awaiting_review: 2,
      },
    }
    lecturerApi.courses.mockResolvedValue([])
    lecturerApi.quizzes.mockResolvedValue([monitoredQuiz])
    const { default: Quizzes } = await import('../Quizzes')
    renderAt(<Quizzes />)
    const link = await screen.findByRole('link', { name: 'Monitoring & activity' })
    expect(link).toHaveAttribute('href', `/lecturer/quizzes/${monitoredQuiz.id}?step=monitoring`)
    expect(screen.getByText('2 awaiting review')).toBeInTheDocument()

    lecturerApi.quiz.mockResolvedValue(monitoredQuiz)
    lecturerApi.quizMonitoring.mockResolvedValue({
      quiz_id: monitoredQuiz.id, quiz_title: monitoredQuiz.title,
      settings: { tab: true, fullscreen: 'off', camera: true, microphone: false },
      rules: { algorithm: 'monitor-rules-v1', needs_review_when: [], note: '' },
      retention_days: 180, totals: { needs_review: 1, event_recorded: 1, normal: 1 }, students: [],
    })
    const { default: QuizDetail } = await import('../QuizDetail')
    renderAt(<QuizDetail />, { path: '/lecturer/quizzes/:quizId', route: `/lecturer/quizzes/${monitoredQuiz.id}` })
    expect(await screen.findByText(/3 monitored attempts/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Open monitoring & activity' }))
    expect(await screen.findByRole('tab', { name: /Monitoring & activity \(2 awaiting review\)/ })).toHaveAttribute('aria-selected', 'true')
  })
})
