import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent, waitFor, render } from '@testing-library/react'
import aiAnswer from '../../../../../docs/api-samples/insights_answer_ai.json'
import rulesAnswer from '../../../../../docs/api-samples/insights_answer_rules.json'
import agentRun from '../../../../../docs/api-samples/insights_agent_run.json'
import genSteps from '../../../../../docs/api-samples/generation_agent_steps.json'
import mismatchRun from '../../../../../docs/api-samples/generation_status_quality_mismatch.json'
import { renderAt } from '../../../pages/lecturer/__tests__/helpers'

vi.mock('../../../api/endpoints', () => ({
  lecturerApi: { quizzes: vi.fn(), askClass: vi.fn(), agentRun: vi.fn(), generationAgent: vi.fn() },
}))

const { lecturerApi } = await import('../../../api/endpoints')
const { default: AskClass } = await import('../AskClass')
const { default: GenerationProgress } = await import('../../quiz/GenerationProgress')

beforeEach(() => {
  vi.clearAllMocks()
  lecturerApi.quizzes.mockResolvedValue([{ id: 1, title: 'Scheduling quiz', status: 'published' }, { id: 2, title: 'Draft', status: 'draft' }])
})

describe('Ask about your class', () => {
  it('sends the question and shows the answer, the tools used and the limits', async () => {
    lecturerApi.askClass.mockResolvedValue(aiAnswer.body)
    renderAt(<AskClass courseId="1" />)
    fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'Which students need help?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() => expect(lecturerApi.askClass).toHaveBeenCalledWith({ course_id: 1, quiz_id: null, question: 'Which students need help?' }))
    expect(await screen.findByText(aiAnswer.body.answer)).toBeInTheDocument()
    expect(screen.getByText('Check in with Sample Student B about CPU Scheduling.')).toBeInTheDocument()
    expect(screen.getByText('Limits of this answer')).toBeInTheDocument()
    expect(screen.getByText('Worded by AI (grok-test)')).toBeInTheDocument()
    expect(screen.getByText('Read student performance (anonymised)')).toBeInTheDocument()
    expect(screen.getByText(/Every number in this answer was checked/)).toBeInTheDocument()
  })

  it('says when the answer came from fixed rules and why', async () => {
    lecturerApi.askClass.mockResolvedValue(rulesAnswer.body)
    renderAt(<AskClass courseId="1" />)
    fireEvent.click(screen.getByText('Which students may need support?'))
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText('Fixed rules (no AI)')).toBeInTheDocument()
    expect(screen.getByText('AI not used: No AI model is set up (GROK_API_KEY is empty).')).toBeInTheDocument()
    expect(screen.queryByText(/Every number in this answer was checked/)).toBeNull()
  })

  it('limits a question to one published quiz when chosen', async () => {
    lecturerApi.askClass.mockResolvedValue(rulesAnswer.body)
    renderAt(<AskClass courseId="1" />)
    await screen.findByRole('option', { name: 'Scheduling quiz' })
    expect(screen.queryByRole('option', { name: 'Draft' })).toBeNull()
    fireEvent.change(screen.getByLabelText('Quiz (optional)'), { target: { value: '1' } })
    fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'How did it go?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    await waitFor(() => expect(lecturerApi.askClass).toHaveBeenCalledWith({ course_id: 1, quiz_id: 1, question: 'How did it go?' }))
  })

  it('shows the agent steps on request', async () => {
    lecturerApi.askClass.mockResolvedValue(aiAnswer.body)
    lecturerApi.agentRun.mockResolvedValue(agentRun.body)
    renderAt(<AskClass courseId="1" />)
    fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'Which students need help?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    fireEvent.click(await screen.findByRole('button', { name: "Show the agent's steps" }))
    await waitFor(() => expect(lecturerApi.agentRun).toHaveBeenCalledWith(aiAnswer.body.agent_run_id))
    expect(await screen.findByText('AI picks the tools')).toBeInTheDocument()
    expect(screen.getByText('Accept the AI’s answer')).toBeInTheDocument()
    expect(screen.getByText('Every number in the AI\'s answer appears in the tool results.')).toBeInTheDocument()
  })

  it('shows an error without losing the question', async () => {
    lecturerApi.askClass.mockRejectedValue(Object.assign(new Error('Too many questions. Try again in 30 seconds.'), { status: 429 }))
    renderAt(<AskClass courseId="1" />)
    fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'Hello there' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText(/Too many questions/)).toBeInTheDocument()
    expect(screen.getByLabelText('Your question')).toHaveValue('Hello there')
  })
})

describe('Generation agent log', () => {
  it('loads the steps of a finished run and explains each decision', async () => {
    lecturerApi.generationAgent.mockResolvedValue(genSteps.body)
    render(<GenerationProgress run={mismatchRun.body} />)
    fireEvent.click(screen.getByRole('button', { name: 'What the generation agent did' }))
    await waitFor(() => expect(lecturerApi.generationAgent).toHaveBeenCalledWith(mismatchRun.body.run_id))
    expect((await screen.findAllByText('Generate a question (Qwen)')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Try this question again').length).toBeGreaterThan(0)
    expect(screen.getByText('Wait for your review (never publishes)')).toBeInTheDocument()
  })

  it('is not offered on student practice', () => {
    render(<GenerationProgress run={mismatchRun.body} showQuality={false} />)
    expect(screen.queryByRole('button', { name: 'What the generation agent did' })).toBeNull()
  })
})
