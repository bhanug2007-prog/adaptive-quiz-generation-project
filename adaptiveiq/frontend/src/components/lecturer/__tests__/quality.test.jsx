import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor, render } from '@testing-library/react'
import failedQ from '../../../../../docs/api-samples/lecturer_question_failed_checks.json'
import passedQ from '../../../../../docs/api-samples/lecturer_question_ai_passed.json'
import mismatchRun from '../../../../../docs/api-samples/generation_status_quality_mismatch.json'
import { renderAt } from '../../../pages/lecturer/__tests__/helpers'

vi.mock('../../../api/endpoints', () => ({
  lecturerApi: {
    reviewQuestion: vi.fn(), checkQuality: vi.fn(), questionHistory: vi.fn(), duplicateQuestion: vi.fn(),
    deleteQuestion: vi.fn(), editQuestion: vi.fn(),
  },
}))

const { lecturerApi } = await import('../../../api/endpoints')
const { default: QuestionReview } = await import('../QuestionReview')
const { default: QuestionCard } = await import('../QuestionCard')
const { default: GenerationProgress } = await import('../../quiz/GenerationProgress')

beforeEach(() => { vi.clearAllMocks() })

describe('AI review on the review screen', () => {
  it('marks a kept question as failed, with the reason and the reviewer feedback', () => {
    renderAt(<QuestionCard q={failedQ.body} index={1} />)
    expect(screen.getAllByText('Failed checks').length).toBeGreaterThan(0)
    expect(screen.getByText('AI review failed')).toBeInTheDocument()
    expect(screen.getByRole('note')).toHaveTextContent('AI review: difficulty differs from the one requested (asked for easy, judged hard). It was kept')
    expect(screen.getByRole('note')).toHaveTextContent('AI reviewer: Fine for an exam.')
    fireEvent.click(screen.getByText('Checks, source and model'))
    expect(screen.getByText('Judged difficulty').nextSibling).toHaveTextContent('hard')
    expect(screen.getByText('AI review').nextSibling).toHaveTextContent('AI review failed by grok-test, score 88 / 100')
  })

  it('shows a passed review with its score and no failure note', () => {
    renderAt(<QuestionCard q={passedQ.body} index={2} />)
    expect(screen.getByText('AI review passed (88)')).toBeInTheDocument()
    expect(screen.queryByText('Failed checks')).toBeNull()
    expect(screen.queryByRole('note')).toBeNull()
  })

  it('says when the AI review was not done, and why', () => {
    const q = { ...passedQ.body, validation: { ...passedQ.body.validation, quality: { status: 'not_checked', evaluator: null, ai_error: 'No AI reviewer is set up (GROK_API_KEY is empty).' } } }
    renderAt(<QuestionCard q={q} />)
    expect(screen.getByText('AI review not done')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Checks, source and model'))
    expect(screen.getByText('AI review').nextSibling).toHaveTextContent('Not done: No AI reviewer is set up (GROK_API_KEY is empty).')
  })

  it('asks before approving a question that failed the checks', async () => {
    lecturerApi.reviewQuestion.mockResolvedValue({ ...failedQ.body, review_status: 'approved' })
    const onChanged = vi.fn()
    renderAt(<QuestionReview q={failedQ.body} index={1} onChanged={onChanged} />)
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(lecturerApi.reviewQuestion).not.toHaveBeenCalled()
    expect(await screen.findByText('Approve a question that failed the checks?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Approve anyway' }))
    await waitFor(() => expect(lecturerApi.reviewQuestion).toHaveBeenCalledWith(failedQ.body.id, 'approve', null))
    expect(onChanged).toHaveBeenCalled()
  })

  it('disables Approve when numerical verification failed or is unchecked', () => {
    const wrongMath = {
      ...failedQ.body,
      validation: {
        ...failedQ.body.validation,
        math_status: 'wrong_key',
        math_verified: false,
        failed_validation: true,
        failure_reason: 'math_wrong_key',
        failure_text: 'Python check found a different correct option',
      },
    }
    const { rerender } = renderAt(<QuestionReview q={wrongMath} index={1} />)
    const btn1 = screen.getByRole('button', { name: 'Approve' })
    expect(btn1).toBeDisabled()
    fireEvent.click(btn1)
    expect(lecturerApi.reviewQuestion).not.toHaveBeenCalled()

    const uncheckedMath = {
      ...passedQ.body,
      review_status: 'draft',
      validation: {
        ...passedQ.body.validation,
        math_status: 'unchecked',
        math_verified: false,
      },
    }
    rerender(<QuestionReview q={uncheckedMath} index={1} />)
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
  })

  it('approves a passed question straight away', async () => {
    lecturerApi.reviewQuestion.mockResolvedValue({ ...passedQ.body, review_status: 'approved' })
    renderAt(<QuestionReview q={passedQ.body} index={2} />)
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(lecturerApi.reviewQuestion).toHaveBeenCalledWith(passedQ.body.id, 'approve', null))
  })

  it('checks a question again and shows the new result', async () => {
    const fixed = { ...failedQ.body, validation: { ...passedQ.body.validation } }
    lecturerApi.checkQuality.mockResolvedValue(fixed)
    const onChanged = vi.fn()
    renderAt(<QuestionReview q={failedQ.body} index={1} onChanged={onChanged} />)
    fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
    await waitFor(() => expect(lecturerApi.checkQuality).toHaveBeenCalledWith(failedQ.body.id))
    expect(onChanged).toHaveBeenCalledWith(fixed)
    expect(await screen.findByText('Checked: AI review passed')).toBeInTheDocument()
  })

  it('shows uploaded document source page and section reference on QuestionCard', () => {
    const docQ = {
      ...passedQ.body,
      source_type: 'document',
      source_excerpt: 'Round robin scheduling assigns a fixed time quantum.',
      source_ref: { document_name: 'os_chapters.pdf', file_type: 'pdf', page: 4, section: 'CPU Scheduling' },
    }
    renderAt(<QuestionCard q={docQ} index={1} />)
    expect(screen.getAllByText(/os_chapters\.pdf · p\. 4 · CPU Scheduling/).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByText('Checks, source and model'))
    expect(screen.getByText('Source').nextSibling).toHaveTextContent('From uploaded document')
    expect(screen.getByText('Source reference').nextSibling).toHaveTextContent('os_chapters.pdf · p. 4 · CPU Scheduling')
  })
})

describe('Run summary', () => {
  it('compares the requested and judged difficulty mix and counts kept failures', () => {
    render(<GenerationProgress run={mismatchRun.body} />)
    expect(screen.getByText(/AI review: used on every question \(grok-test\)/)).toBeInTheDocument()
    expect(screen.getByText(/Difficulty mix requested: 1 easy, 1 hard\. Judged by the AI reviewer: 2 hard, which does not match \(1 question differs\)\./)).toBeInTheDocument()
    expect(screen.getByText(/1 question kept with "Failed checks"\./)).toBeInTheDocument()
  })

  it('is hidden when asked (student practice)', () => {
    render(<GenerationProgress run={mismatchRun.body} showQuality={false} />)
    expect(screen.queryByText(/Difficulty mix requested/)).toBeNull()
  })
})
