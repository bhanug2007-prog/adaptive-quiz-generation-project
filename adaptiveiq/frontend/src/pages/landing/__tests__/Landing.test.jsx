import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import Landing from '../Landing'
import PublicLayout from '../../../layouts/PublicLayout'
import UiText from '../../../components/landing/UiText'

// The landing page is public and must never call the API; fail loudly if it does.
vi.mock('../../../api/endpoints', () => new Proxy({}, { get: () => () => { throw new Error('landing must not call the API') } }))
vi.mock('../../../auth/AuthProvider', () => ({
  useAuth: () => ({ user: null }),
  homeFor: (u) => (u?.role === 'lecturer' ? '/lecturer' : '/student'),
}))

const renderPage = () => render(
  <MemoryRouter initialEntries={['/']}>
    <Routes>
      <Route element={<PublicLayout />}>
        <Route index element={<Landing />} />
      </Route>
    </Routes>
  </MemoryRouter>,
)

describe('Landing page', () => {
  it('has the hero copy and the two ways in', () => {
    renderPage()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Turn your syllabus into a smarter way to learn.')
    expect(screen.getByText('Generate quizzes, track topic mastery, and focus on what you need to improve.')).toBeInTheDocument()
    const getStarted = screen.getAllByRole('link', { name: /Get Started/ })
    expect(getStarted.length).toBeGreaterThanOrEqual(3)
    getStarted.forEach((a) => expect(a).toHaveAttribute('href', '/register'))
    screen.getAllByRole('link', { name: /^Sign in$/ }).forEach((a) => expect(a).toHaveAttribute('href', '/signin'))
    expect(screen.getByRole('link', { name: 'Explore the Platform' })).toHaveAttribute('href', '#product')
  })

  it('has every section the navigation links to', () => {
    renderPage()
    const nav = screen.getByRole('navigation', { name: 'Main' })
    const hrefs = within(nav).getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(hrefs).toEqual(['/#product', '/#features', '/#experience', '/#how'])
    for (const id of ['product', 'features', 'experience', 'how']) {
      expect(document.getElementById(id), `missing #${id}`).not.toBeNull()
    }
  })

  it('uses the requested feature, role and step wording', () => {
    renderPage()
    const features = document.getElementById('features')
    for (const t of ['Quiz Generation', 'Adaptive Practice', 'Learning Analytics']) {
      expect(within(features).getByRole('heading', { name: t })).toBeInTheDocument()
    }
    expect(features).toHaveTextContent('Turn topics or learning material into multiple-choice questions.')
    const exp = document.getElementById('experience')
    expect(within(exp).getByText('For lecturers')).toBeInTheDocument()
    expect(within(exp).getByText('For students')).toBeInTheDocument()
    const how = document.getElementById('how')
    for (const t of ['Select a topic.', 'Generate or take a quiz.', 'Review results and improve.']) {
      expect(within(how).getByRole('heading', { name: t })).toBeInTheDocument()
    }
    expect(screen.getByRole('heading', { name: 'Make every practice session count.' })).toBeInTheDocument()
  })

  it('describes every preview for screen readers', () => {
    const { container } = renderPage()
    const previews = container.querySelectorAll('figure.mk')
    expect(previews.length).toBeGreaterThan(5)
    previews.forEach((f) => expect(f.getAttribute('aria-label')).toMatch(/^Preview of /))
  })

  it('opens and closes the mobile menu', () => {
    renderPage()
    const btn = screen.getByRole('button', { name: 'Open menu' })
    expect(btn).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(btn)
    expect(screen.getByRole('button', { name: 'Close menu' })).toHaveAttribute('aria-expanded', 'true')
    expect(document.getElementById('site-menu')).not.toBeNull()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(document.getElementById('site-menu')).toBeNull()
  })

  it('is honest about AI and sample data', () => {
    renderPage()
    expect(screen.getAllByText(/use sample data\./).length).toBeGreaterThan(0)
    expect(document.getElementById('experience')).toHaveTextContent(/Publish only after every question is approved/)
    expect(document.getElementById('product')).toHaveTextContent(/Fewer than 5 different questions/)
    expect(document.getElementById('how')).toHaveTextContent(/only after the lecturer approves every question/)
  })

  it('makes no accuracy, usage or testimonial claims', () => {
    const { container } = renderPage()
    expect(container.textContent).not.toMatch(/\d+% accura|accuracy of|students use|trusted by|testimonial|\d+\+ (students|users|schools)/i)
    expect(container.querySelector('canvas')).toBeNull()
  })

  it('keeps the team credit without the guide name', () => {
    const { container } = renderPage()
    expect(screen.getByText('A DSAI team project at IIIT Dharwad.')).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/Utkarsh|Khaire/)
  })
})

describe('UiText', () => {
  it('renders [[labels]] as app labels', () => {
    const { container } = render(<p><UiText text="Open [[My Courses]] and press [[Join course]]." /></p>)
    const labels = container.querySelectorAll('.lp2-ui')
    expect([...labels].map((l) => l.textContent)).toEqual(['My Courses', 'Join course'])
    expect(container.textContent).toBe('Open My Courses and press Join course.')
  })
})
