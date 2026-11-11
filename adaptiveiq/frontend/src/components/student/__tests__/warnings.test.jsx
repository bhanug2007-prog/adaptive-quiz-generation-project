import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ActivityWarnings, MonitoringStatus } from '../Monitoring'

const record = (n) => ({ warning_count: n, warning_threshold: 3, review_required: n >= 3,
  warning_history: Array.from({ length: n }, (_, i) => ({ seq: i + 1, kind: 'face_multiple', at: '2026-11-10T09:00:00Z' })) })

it('shows first, second, third accessible red warning with a persistent review notice', () => {
  const mon = { enabled: true, started: true, cfg: {}, devices: {}, record: record(1) }
  const { rerender } = render(<><MonitoringStatus mon={mon} /><ActivityWarnings mon={mon} /></>)
  expect(screen.getByRole('alert')).toHaveClass('st-activity-warning')
  expect(screen.getByRole('alert')).toHaveTextContent('Activity warning 1 of 3')
  expect(screen.getByText('Alerts: 1 / 3')).toBeVisible()
  rerender(<ActivityWarnings mon={{ ...mon, record: record(2) }} />)
  expect(screen.getByRole('alert')).toHaveTextContent('Activity warning 2 of 3')
  rerender(<ActivityWarnings mon={{ ...mon, record: record(3) }} />)
  expect(screen.getByRole('alert')).toHaveTextContent('Lecturer review required. You can continue answering.')
  expect(screen.getByRole('alert')).toHaveTextContent('does not submit your quiz or change your marks')
})

it('reports a false alert without removing history and retries with the same report ID', async () => {
  const reportProblem = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ saved: true })
  render(<ActivityWarnings mon={{ enabled: true, record: record(1), reportProblem }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Report a false alert or device problem' }))
  fireEvent.change(screen.getByLabelText('Related warning'), { target: { value: '1' } })
  fireEvent.change(screen.getByLabelText('Details (optional)'), { target: { value: 'Mirror reflection' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send report' }))
  await screen.findByText(/Could not save your report/)
  fireEvent.click(screen.getByRole('button', { name: 'Send report' }))
  await screen.findByText(/Report saved for your lecturer/)
  expect(reportProblem.mock.calls[0][0]).toEqual(reportProblem.mock.calls[1][0])
  expect(reportProblem.mock.calls[1][0]).toMatchObject({ category: 'false_alert', event_seq: 1, note: 'Mirror reflection' })
  expect(screen.getByRole('alert')).toHaveTextContent('Activity warning 1 of 3')
})

it('renders nothing for practice and shows pending sync without inventing a count', () => {
  const { rerender, container } = render(<ActivityWarnings mon={{ enabled: false }} />)
  expect(container).toBeEmptyDOMElement()
  rerender(<ActivityWarnings mon={{ enabled: true, syncError: true, record: record(1) }} />)
  expect(screen.getByText(/Monitoring sync pending/)).toBeVisible()
  expect(screen.getByText(/Activity warning 1 of 3/)).toBeVisible()
})
