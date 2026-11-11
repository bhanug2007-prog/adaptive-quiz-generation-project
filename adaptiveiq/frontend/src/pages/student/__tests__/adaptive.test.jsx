// Phase 5: the student's difficulty and subject breakdowns, the explained difficulty history, and often-skipped topics.
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../api/endpoints', () => ({
  studentApi: { weakAreas: vi.fn(), trends: vi.fn(), mastery: vi.fn(), masteryHistory: vi.fn() },
  topicsApi: {}, generationApi: {}, healthApi: {}, authApi: {},
}))
const { studentApi } = await import('../../../api/endpoints')
const { Breakdown, DifficultyHistory } = await import('../Progress')
const { WeakAreas } = await import('../Insights')

const trends = {
  breakdown_note: 'Only quizzes whose results have been released.',
  by_difficulty: [
    { difficulty: 'easy', correct: 2, answered: 2, skipped: 0, accuracy: 1 },
    { difficulty: 'medium', correct: 1, answered: 2, skipped: 1, accuracy: 0.5 },
    { difficulty: 'hard', correct: 0, answered: 0, skipped: 0, accuracy: null },
  ],
  by_subject: [{ subject: 'OS', correct: 3, answered: 4, skipped: 1, topics: 1, accuracy: 0.75 }],
}

beforeEach(() => vi.clearAllMocks())

describe('Breakdown', () => {
  it('shows accuracy by difficulty and subject with skipped answers apart', () => {
    render(<Breakdown t={trends} />)
    expect(screen.getByText('Only quizzes whose results have been released.')).toBeInTheDocument()
    const medium = screen.getByText('Medium').closest('tr')
    expect(within(medium).getAllByRole('cell').map((c) => c.textContent)).toEqual(['Medium', '2', '50%', '1'])
    const hard = screen.getByText('Hard').closest('tr')
    expect(within(hard).getAllByRole('cell')[2].textContent).toBe('—')
    const os = screen.getByText('OS').closest('tr')
    expect(within(os).getAllByRole('cell').map((c) => c.textContent)).toEqual(['OS', '1', '4', '75%', '1'])
  })
  it('says so when nothing is released yet', () => {
    render(<Breakdown t={{ ...trends, by_difficulty: trends.by_difficulty.map((d) => ({ ...d, answered: 0, skipped: 0 })), by_subject: [] }} />)
    expect(screen.getByText('No released results yet.')).toBeInTheDocument()
  })
})

describe('DifficultyHistory', () => {
  it('lists each change with its reason, newest first', () => {
    render(<DifficultyHistory points={[
      { at: '2026-11-01T10:00:00Z', next_difficulty: 'medium', previous_difficulty: null, difficulty_reason: 'Start at medium.' },
      { at: '2026-11-02T10:00:00Z', next_difficulty: 'hard', previous_difficulty: 'medium', difficulty_reason: '5 of your last 5 correct.' },
    ]} />)
    const items = screen.getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Medium → Hard')
    expect(items[0]).toHaveTextContent('5 of your last 5 correct.')
    expect(items[1]).toHaveTextContent('Start at medium.')
  })
  it('shows nothing without decisions', () => {
    const { container } = render(<DifficultyHistory points={[{ at: '2026-11-01T10:00:00Z', next_difficulty: 'medium' }]} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('WeakAreas', () => {
  it('lists often-skipped topics separately from weak ones', async () => {
    studentApi.weakAreas.mockResolvedValue({ weak: [], developing: [], insufficient_evidence: [], ok: [{ topic_key: 't:1' }], not_attempted: [],
      often_skipped: [{ topic_key: 't:2', topic: 'Deadlocks', subject: 'OS', skipped: 3, answers: 5, skipped_pct: 60 }],
      often_skipped_rule: 'At least 5 questions and 30% or more left blank.' })
    render(<MemoryRouter><WeakAreas /></MemoryRouter>)
    expect(await screen.findByText('Often left blank (1)')).toBeInTheDocument()
    expect(screen.getByText(/3 of 5 questions skipped \(60%\)/)).toBeInTheDocument()
    expect(screen.queryByText('Weak areas', { exact: false })).not.toBeInTheDocument()
  })
  it('keeps the empty state when nothing is weak or skipped', async () => {
    studentApi.weakAreas.mockResolvedValue({ weak: [], developing: [], insufficient_evidence: [], ok: [{ topic_key: 't:1' }], not_attempted: [], often_skipped: [] })
    render(<MemoryRouter><WeakAreas /></MemoryRouter>)
    expect(await screen.findByText('No weak areas right now')).toBeInTheDocument()
  })
})
