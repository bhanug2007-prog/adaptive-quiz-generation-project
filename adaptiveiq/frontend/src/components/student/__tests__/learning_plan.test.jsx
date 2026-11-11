import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../../api/endpoints', () => ({
  studentApi: {
    learningPlanPreview: vi.fn(),
    learningPlanCurrent: vi.fn(),
    learningPlanCreate: vi.fn(),
    learningPlanGet: vi.fn(),
    learningPlanApprove: vi.fn(),
    learningPlanDismiss: vi.fn(),
    learningPlanPostpone: vi.fn(),
    learningPlanRefresh: vi.fn(),
    weakAreas: vi.fn(),
    revision: vi.fn(),
    questionStatus: vi.fn(),
    recommendations: vi.fn(),
    studyPlan: vi.fn(),
    confidence: vi.fn(),
  },
  topicsApi: {},
  generationApi: {},
  healthApi: {},
  authApi: {},
}))

const { studentApi } = await import('../../../api/endpoints')
const { default: LearningPlan } = await import('../LearningPlan')
const { default: Insights } = await import('../../../pages/student/Insights')

function LocationProbe() {
  const loc = useLocation()
  return <div data-testid="loc">{`${loc.pathname}${loc.search}`}</div>
}

const samplePlan = {
  agent: 'personalized_learning',
  stage: 1,
  mode: 'deterministic_preview',
  llm_used: false,
  read_only: true,
  graph_version: 'langgraph-plan-v1',
  policy_versions: {
    mastery: 'mastery-beta-v3',
    difficulty: 'difficulty-policy-v1',
    weak_areas: 'weak-rules-v2',
    recommendations: 'reco-rules-v2',
    revision: 'leitner-v1',
  },
  generated_at: '2026-11-10T10:00:00Z',
  scenario: 'weak_prerequisite',
  scenarios: ['sufficient_evidence', 'insufficient_evidence', 'weak_prerequisite', 'due_revision', 'weekly_budget_applied'],
  routing_mode: 'prioritize_remediation',
  summary: {
    headline: "Start with prerequisite 'Processes' before revisiting 'CPU Scheduling'.",
    rationale: 'Built deterministically across 3 prioritized session(s) fitted to 4 h/week (240 min total). Includes 2 due Leitner revision question(s).',
    weekly_study_hours: 4,
    weekly_hours_source: 'profile',
    budget_status: 'allocated',
    allocated_minutes: 240,
    allocated_hours: 4.0,
    due_revision_total: 2,
    upcoming_revision_total: 1,
    insufficient_evidence_topics: 1,
    weak_prerequisite_topics: 1,
    sufficient_evidence_topics: 2,
    empty_reason: null,
  },
  items: [
    {
      rank: 1,
      activity_id: 'prerequisite:t:1',
      kind: 'prerequisite',
      topic_key: 't:1',
      topic: 'Processes',
      subject: 'Operating Systems',
      course_id: 1,
      topic_id: 1,
      quiz_id: null,
      status: 'weak',
      mastery_label: 'needs_improvement',
      mastery_score_pct: 38,
      evidence_sufficient: true,
      unique_questions: 6,
      min_evidence: 5,
      recommended_difficulty: 'easy',
      priority: 1.32,
      estimated_minutes: 95,
      estimated_hours: 1.58,
      reason: 'Review Processes first: it is a prerequisite of CPU Scheduling, where estimated mastery is 42% across 5 questions.',
      due_revision_count: 0,
      prerequisite_of: ['CPU Scheduling'],
      blocked_by_prerequisite: null,
      next_action: {
        label: 'Review Processes (easy)',
        action_type: 'prefill_practice',
        target_href: '/student/practice?subject=Operating+Systems&topic=Processes&topic_id=1&difficulty=easy',
        prefill: { subject: 'Operating Systems', topic: 'Processes', topic_id: 1, difficulty: 'easy' },
        read_only_preview: true,
        requires_approval: false,
      },
    },
    {
      rank: 2,
      activity_id: 'revisit_incorrect:t:2',
      kind: 'revisit_incorrect',
      topic_key: 't:2',
      topic: 'CPU Scheduling',
      subject: 'Operating Systems',
      course_id: 1,
      topic_id: 2,
      quiz_id: null,
      status: 'weak',
      mastery_label: 'needs_improvement',
      mastery_score_pct: 42,
      evidence_sufficient: true,
      unique_questions: 5,
      min_evidence: 5,
      recommended_difficulty: 'mixed',
      priority: 1.0,
      estimated_minutes: 90,
      estimated_hours: 1.5,
      reason: '2 question(s) you missed on CPU Scheduling are due for spaced revision.',
      due_revision_count: 2,
      prerequisite_of: [],
      blocked_by_prerequisite: 'Processes',
      next_action: {
        label: 'Start spaced revision (2 due)',
        action_type: 'navigate_revision',
        target_href: '/student/insights#revision',
        prefill: { topic: 'CPU Scheduling', subject: 'Operating Systems', due: 2 },
        read_only_preview: true,
        requires_approval: false,
      },
    },
    {
      rank: 3,
      activity_id: 'gather_evidence:t:3',
      kind: 'gather_evidence',
      topic_key: 't:3',
      topic: 'Deadlocks',
      subject: 'Operating Systems',
      course_id: 1,
      topic_id: 3,
      quiz_id: null,
      status: 'insufficient_evidence',
      mastery_label: 'insufficient_evidence',
      mastery_score_pct: null,
      evidence_sufficient: false,
      unique_questions: 2,
      min_evidence: 5,
      recommended_difficulty: 'mixed',
      priority: 0.1,
      estimated_minutes: 55,
      estimated_hours: 0.92,
      reason: 'Try a mixed quiz on Deadlocks: only 2 question(s) answered; more practice is needed to judge. Answer at least 3 more different question(s) before locking difficulty.',
      due_revision_count: 0,
      prerequisite_of: [],
      blocked_by_prerequisite: null,
      next_action: {
        label: 'Gather evidence on Deadlocks (mixed)',
        action_type: 'prefill_practice',
        target_href: '/student/practice?subject=Operating+Systems&topic=Deadlocks&topic_id=3&difficulty=mixed',
        prefill: { subject: 'Operating Systems', topic: 'Deadlocks', topic_id: 3, difficulty: 'mixed' },
        read_only_preview: true,
        requires_approval: false,
      },
    },
  ],
  deferred_topics: [
    { topic_key: 't:4', topic: 'Virtual Memory', subject: 'Operating Systems', kind: 'developing', reason: 'Deferred so top-priority activities fit within your 4 h/week schedule.' },
  ],
  proposed_next_actions: [
    {
      label: 'Review Processes (easy)',
      action_type: 'prefill_practice',
      target_href: '/student/practice?subject=Operating+Systems&topic=Processes&topic_id=1&difficulty=easy',
      prefill: null,
      read_only_preview: true,
      requires_approval: false,
    },
    {
      label: 'Start spaced revision (2 due)',
      action_type: 'navigate_revision',
      target_href: '/student/insights#revision',
      prefill: null,
      read_only_preview: true,
      requires_approval: false,
    },
  ],
  warnings: [
    'Fewer than 5 distinct questions answered on Deadlocks; estimates are tentative until more evidence is gathered.',
    '1 lower-priority topic(s) were deferred to keep this plan realistic.',
  ],
  graph_trace: {
    nodes_visited: [
      'authenticate_and_load_evidence',
      'build_candidate_activities',
      'validate_recommendations_and_permissions',
      'construct_personalized_plan',
      'return_plan_preview',
    ],
    edges_taken: [
      {
        from_node: 'validate_recommendations_and_permissions',
        condition: 'prioritize_remediation',
        to_node: 'construct_personalized_plan',
        reason: "Constructing ordered study plan under 'prioritize_remediation' strategy.",
      },
    ],
  },
}

const sampleStage2Plan = {
  id: 14,
  agent: 'personalized_learning',
  stage: 2,
  mode: 'persistent_hitl',
  llm_used: false,
  graph_version: 'langgraph-plan-v2',
  policy_versions: samplePlan.policy_versions,
  status: 'awaiting_approval',
  action_approval_status: 'pending',
  selected_activity_id: 'prerequisite:t:1',
  generation_seq: 1,
  last_refreshed_at: null,
  created_at: '2026-11-10T10:05:00Z',
  updated_at: '2026-11-10T10:05:00Z',
  scenario: 'weak_prerequisite',
  scenarios: samplePlan.scenarios,
  routing_mode: 'prioritize_remediation',
  scope_course_ids: [1],
  summary: {
    ...samplePlan.summary,
    allocated_minutes: 180,
    allocated_hours: 3.0,
  },
  progress: {
    total_items: 2,
    pending_items: 2,
    in_progress_items: 0,
    completed_items: 0,
    dismissed_items: 0,
    postponed_items: 0,
    completion_pct: 0,
  },
  pending_approval: {
    awaiting_approval: true,
    default_activity_id: 'prerequisite:t:1',
    actionable_activity_ids: ['prerequisite:t:1', 'revisit_incorrect:t:2'],
    prompt: 'Approve next step: Processes (Start Recommended Practice (easy)) — or postpone, dismiss, or refresh.',
  },
  items: [
    {
      ...samplePlan.items[0],
      id: 101,
      revision_epoch: 1,
      change_status: 'initial',
      is_refreshed_new: false,
      item_status: 'pending',
      approval_status: 'awaiting_approval',
      approved_action_type: 'start_practice',
      can_approve: true,
      can_dismiss: true,
      can_postpone: true,
      postponed_until: null,
      decision_note: null,
      execution_ref: null,
      completed_at: null,
      next_action: {
        label: 'Start Recommended Practice (easy)',
        action_type: 'start_practice',
        target_href: '/student/practice?subject=Operating+Systems&topic=Processes&topic_id=1&difficulty=easy',
        prefill: { subject: 'Operating Systems', topic: 'Processes', topic_id: 1, difficulty: 'easy' },
        read_only_preview: false,
        requires_approval: true,
      },
    },
    {
      ...samplePlan.items[1],
      id: 102,
      revision_epoch: 1,
      change_status: 'initial',
      is_refreshed_new: false,
      item_status: 'pending',
      approval_status: 'awaiting_approval',
      approved_action_type: 'start_revision',
      can_approve: true,
      can_dismiss: true,
      can_postpone: true,
      postponed_until: null,
      decision_note: null,
      execution_ref: null,
      completed_at: null,
      next_action: {
        label: 'Start Due Revision (2 due)',
        action_type: 'start_revision',
        target_href: '/student/insights#revision',
        prefill: { topic_key: 't:2', topic: 'CPU Scheduling', due: 2 },
        read_only_preview: false,
        requires_approval: true,
      },
    },
  ],
  previous_items: [],
  deferred_topics: [],
  proposed_next_actions: [],
  warnings: [],
  last_execution: null,
  graph_trace: {
    nodes_visited: [
      'authenticate_and_load_evidence',
      'build_candidate_activities',
      'validate_recommendations_and_permissions',
      'construct_personalized_plan',
      'prepare_persistent_plan',
    ],
    edges_taken: samplePlan.graph_trace.edges_taken,
  },
}

beforeEach(() => {
  vi.clearAllMocks()
  studentApi.learningPlanCurrent.mockResolvedValue(null)
})

describe('LearningPlan Stage 1 preview', () => {
  it('renders recommended topics, reasons, estimated time, prerequisite order, and Save CTA', async () => {
    studentApi.learningPlanPreview.mockResolvedValue(samplePlan)
    render(<MemoryRouter><LearningPlan /></MemoryRouter>)

    expect(await screen.findByText('Personalized Learning Plan')).toBeInTheDocument()
    expect(screen.getByText('Read-only preview')).toBeInTheDocument()
    expect(screen.getByText('4 h/week · 240 min')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Save & Start Learning Plan/i })).toBeInTheDocument()

    const list = screen.getByRole('list', { name: 'Personalized study sessions' })
    const items = within(list).getAllByRole('listitem')
    expect(items).toHaveLength(3)

    expect(items[0]).toHaveTextContent('Processes')
    expect(items[0]).toHaveTextContent('Prerequisite first')
    expect(items[0]).toHaveTextContent('Mastery 38% · 6 questions')
    expect(items[0]).toHaveTextContent('95 min · 1.58 h')

    expect(items[1]).toHaveTextContent('CPU Scheduling')
    expect(items[1]).toHaveTextContent('Due revision')
    expect(items[1]).toHaveTextContent('Practise after Processes')
    const revLinks = screen.getAllByRole('link', { name: 'Start spaced revision (2 due)' })
    expect(revLinks[0]).toHaveAttribute('href', '#revision')

    expect(items[2]).toHaveTextContent('Deadlocks')
    expect(items[2]).toHaveTextContent('Tentative (2/5 questions for mastery)')
    expect(items[2]).not.toHaveTextContent(/Mastery \d+%/)

    expect(screen.getByLabelText('Proposed next actions')).toBeInTheDocument()
    expect(screen.getByText(/Deferred for now: Virtual Memory/)).toBeInTheDocument()
  })

  it('shows zero-hour warning and Profile link when weekly study hours are 0', async () => {
    studentApi.learningPlanPreview.mockResolvedValue({
      ...samplePlan,
      summary: {
        ...samplePlan.summary,
        weekly_study_hours: 0,
        budget_status: 'zero_hours',
        allocated_minutes: 0,
        allocated_hours: 0,
      },
      items: [{ ...samplePlan.items[0], estimated_minutes: 0, estimated_hours: 0 }],
      warnings: ['Your weekly study hours are set to 0 in Profile, so 0 minutes were scheduled.'],
      proposed_next_actions: [
        {
          label: 'Update weekly study hours in Profile',
          action_type: 'open_profile',
          target_href: '/student/profile',
          prefill: null,
          read_only_preview: true,
          requires_approval: false,
        },
      ],
    })
    render(<MemoryRouter><LearningPlan /></MemoryRouter>)

    expect(await screen.findByText('0 h/week configured')).toBeInTheDocument()
    expect(screen.getByText('0 min')).toBeInTheDocument()
    const profileLink = screen.getByRole('link', { name: 'Update weekly study hours in Profile' })
    expect(profileLink).toHaveAttribute('href', '/student/profile')
  })

  it('renders a safe empty state when no eligible questions or material exist', async () => {
    studentApi.learningPlanPreview.mockResolvedValue({
      ...samplePlan,
      scenario: 'no_eligible_material',
      scenarios: ['no_eligible_material'],
      routing_mode: 'no_eligible_material',
      summary: {
        headline: 'No eligible questions or study material yet.',
        rationale: 'Join a course with your lecturer join code or open Practice Lab.',
        weekly_study_hours: null,
        weekly_hours_source: 'unset',
        budget_status: 'empty',
        allocated_minutes: 0,
        allocated_hours: 0,
        due_revision_total: 0,
        upcoming_revision_total: 0,
        insufficient_evidence_topics: 0,
        weak_prerequisite_topics: 0,
        sufficient_evidence_topics: 0,
        empty_reason: 'No eligible approved quizzes or practice questions are available yet.',
      },
      items: [],
      deferred_topics: [],
      warnings: [],
      proposed_next_actions: [
        { label: 'Join or view courses', action_type: 'open_courses', target_href: '/student/courses', prefill: null, read_only_preview: true, requires_approval: false },
        { label: 'Open Practice Lab', action_type: 'practice_lab', target_href: '/student/practice', prefill: null, read_only_preview: true, requires_approval: false },
      ],
    })
    render(<MemoryRouter><LearningPlan /></MemoryRouter>)

    expect(await screen.findByText('No eligible study material yet')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Join or view courses' })).toHaveAttribute('href', '/student/courses')
    expect(screen.getByRole('link', { name: 'Open Practice Lab' })).toHaveAttribute('href', '/student/practice')
  })

  it('recovers cleanly when retried after an API error', async () => {
    studentApi.learningPlanPreview
      .mockRejectedValueOnce(new Error('Temporary preview outage'))
      .mockResolvedValueOnce(samplePlan)
    render(<MemoryRouter><LearningPlan /></MemoryRouter>)

    expect(await screen.findByText('Temporary preview outage')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Processes')).toBeInTheDocument()
    expect(studentApi.learningPlanPreview).toHaveBeenCalledTimes(2)
  })
})

describe('LearningPlan Stage 2 persistent HITL workflow', () => {
  it('saves a persistent plan from preview and displays Pending Approval and progress', async () => {
    studentApi.learningPlanPreview.mockResolvedValue(samplePlan)
    studentApi.learningPlanCreate.mockResolvedValue(sampleStage2Plan)

    render(<MemoryRouter><LearningPlan /></MemoryRouter>)
    const saveBtn = await screen.findByRole('button', { name: /Save & Start Learning Plan/i })
    fireEvent.click(saveBtn)

    expect(await screen.findByText('Current Plan')).toBeInTheDocument()
    expect(screen.getByText('Awaiting approval')).toBeInTheDocument()
    expect(screen.getByText('Pending Approval')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Learning plan progress' })).toHaveAttribute('aria-valuenow', '0')
    expect(screen.getByRole('button', { name: 'Start Recommended Practice' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start Due Revision' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh Plan' })).toBeInTheDocument()
  })

  it('shows loading state then loads current plan cleanly without exposing checkpoints', async () => {
    let resolveCurrent
    studentApi.learningPlanCurrent.mockImplementation(() => new Promise((res) => { resolveCurrent = res }))

    render(<MemoryRouter><LearningPlan /></MemoryRouter>)
    expect(screen.getByText(/Loading/i) || screen.getByRole('status')).toBeTruthy()

    resolveCurrent(sampleStage2Plan)
    expect(await screen.findByText('Current Plan')).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/lg_checkpoints|thread_id/i)
  })

  it('guards against duplicate approval clicks and navigates safely after backend approval', async () => {
    studentApi.learningPlanCurrent.mockResolvedValue(sampleStage2Plan)
    let resolveApprove
    studentApi.learningPlanApprove.mockImplementation(() => new Promise((res) => { resolveApprove = res }))

    render(
      <MemoryRouter initialEntries={['/student/insights']}>
        <Routes>
          <Route path="/student/insights" element={<LearningPlan />} />
          <Route path="/student/practice" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )

    const approveBtn = await screen.findByRole('button', { name: 'Start Recommended Practice' })
    fireEvent.click(approveBtn)
    fireEvent.click(approveBtn)

    expect(studentApi.learningPlanApprove).toHaveBeenCalledTimes(1)
    expect(studentApi.learningPlanApprove).toHaveBeenCalledWith(14, expect.objectContaining({
      activity_id: 'prerequisite:t:1',
      idempotency_key: expect.any(String),
    }))

    resolveApprove({
      ...sampleStage2Plan,
      status: 'in_progress',
      last_execution: {
        action_type: 'start_practice',
        execution_status: 'started',
        activity_id: 'prerequisite:t:1',
        quiz_id: 88,
        session_id: null,
        generation_run_id: 42,
        destination_href: '/student/practice?run_id=42&topic=Processes',
        reused_existing: false,
        message: 'Started easy practice quiz generation for Processes.',
        executed_at: '2026-11-10T10:06:00Z',
      },
    })

    expect(await screen.findByTestId('loc')).toHaveTextContent('/student/practice?run_id=42&topic=Processes')
  })

  it('supports due revision approval, postpone, dismiss, and refresh with previous-epoch history and error alert', async () => {
    studentApi.learningPlanCurrent.mockResolvedValue(sampleStage2Plan)
    studentApi.learningPlanApprove.mockRejectedValueOnce(new Error('Verification required before starting practice.'))
    studentApi.learningPlanPostpone.mockResolvedValue({
      ...sampleStage2Plan,
      items: [
        { ...sampleStage2Plan.items[0], item_status: 'postponed', approval_status: 'postponed', can_postpone: false, postponed_until: '2026-11-12T10:05:00Z' },
        sampleStage2Plan.items[1],
      ],
      progress: { ...sampleStage2Plan.progress, postponed_items: 1, pending_items: 1 },
    })
    studentApi.learningPlanDismiss.mockResolvedValue({
      ...sampleStage2Plan,
      status: 'dismissed',
      action_approval_status: 'dismissed',
      pending_approval: { awaiting_approval: false, default_activity_id: null, actionable_activity_ids: [], prompt: '' },
      items: sampleStage2Plan.items.map((it) => ({
        ...it, item_status: 'dismissed', approval_status: 'dismissed', can_approve: false, can_dismiss: false, can_postpone: false,
      })),
    })
    studentApi.learningPlanRefresh.mockResolvedValue({
      ...sampleStage2Plan,
      generation_seq: 2,
      status: 'awaiting_approval',
      last_refreshed_at: '2026-11-10T11:30:00Z',
      progress: { total_items: 1, pending_items: 1, in_progress_items: 0, completed_items: 0, dismissed_items: 0, postponed_items: 0, completion_pct: 0 },
      items: [
        {
          ...sampleStage2Plan.items[1],
          id: 201,
          rank: 1,
          revision_epoch: 2,
          kind: 'practice_topic',
          blocked_by_prerequisite: null,
          change_status: 'new',
          is_refreshed_new: true,
        },
      ],
      previous_items: [
        {
          ...sampleStage2Plan.items[0],
          item_status: 'completed',
          completed_at: '2026-11-10T11:00:00Z',
          can_approve: false,
          can_dismiss: false,
          can_postpone: false,
        },
      ],
    })

    render(<MemoryRouter><LearningPlan /></MemoryRouter>)
    await screen.findByText('Current Plan')

    // Action error is presented cleanly via alert without losing the plan
    fireEvent.click(screen.getByRole('button', { name: 'Start Recommended Practice' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Verification required before starting practice.')

    // Postpone first item
    const postponeButtons = screen.getAllByRole('button', { name: 'Postpone' })
    fireEvent.click(postponeButtons[0])
    expect(await screen.findByText('Postponed')).toBeInTheDocument()

    // Refresh plan -> displays New after refresh + previous items drawer
    fireEvent.click(screen.getByRole('button', { name: 'Refresh Plan' }))
    expect(await screen.findByText('New after refresh')).toBeInTheDocument()
    expect(screen.getByText('Previous recommendations (1)')).toBeInTheDocument()
    expect(screen.getByText(/Epoch 1 · Processes/)).toBeInTheDocument()

    // Dismiss plan cleanly
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss Plan' }))
    await waitFor(() => {
      expect(studentApi.learningPlanDismiss).toHaveBeenCalledWith(14, { scope: 'plan' })
    })
  })
})

describe('Insights page integration', () => {
  it('renders Personalized Learning Plan alongside existing Insights sections', async () => {
    studentApi.learningPlanPreview.mockResolvedValue(samplePlan)
    studentApi.weakAreas.mockResolvedValue({ weak: [], developing: [], insufficient_evidence: [], ok: [{ topic_key: 't:1' }], not_attempted: [], often_skipped: [] })
    studentApi.revision.mockResolvedValue({ method: 'Leitner boxes', due: [], upcoming: [] })
    studentApi.questionStatus.mockResolvedValue({ incorrect: [], skipped: [], never_attempted: [] })
    studentApi.recommendations.mockResolvedValue([])
    studentApi.studyPlan.mockResolvedValue({ weekly_hours: 4, items: [], note: null })
    studentApi.confidence.mockResolvedValue({ rated: 0, min_needed: 10, message: 'Rate confidence in practice quizzes.' })

    render(<MemoryRouter><Insights /></MemoryRouter>)

    expect(await screen.findByRole('heading', { name: 'Personalized Learning Plan' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Weak areas' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: "This week's study plan" })).toBeInTheDocument()
  })
})
