/* Shapes copied from docs/api-samples (test fixtures, not real data). */
export const attemptAssessment = {
  session_id: 1, quiz_id: 1, quiz_title: 'Scheduling quiz 1', kind: 'assessment', instructions: null, attempt_no: 1,
  status: 'in_progress', started_at: '2026-10-21T16:43:23.422609Z', deadline_at: null, server_now: '2026-10-21T16:43:23.438473Z',
  confidence_enabled: false, can_check_answers: false,
  questions: [
    { question_id: 3, number: 1, text: 'Which scheduler is non-preemptive by default?', topic: 'CPU Scheduling', difficulty: 'hard', marks: 1.0,
      options: [{ id: 11, label: 'A', text: 'Option gamma 5' }, { id: 10, label: 'B', text: 'Option beta 5' }, { id: 9, label: 'C', text: 'Option alpha 5' }, { id: 12, label: 'D', text: 'Option delta 5' }] },
    { question_id: 5, number: 2, text: 'Which algorithm suits time-sharing systems?', topic: 'CPU Scheduling', difficulty: 'medium', marks: 1.0,
      options: [{ id: 17, label: 'A', text: 'Option alpha 9' }, { id: 18, label: 'B', text: 'Option beta 9' }, { id: 19, label: 'C', text: 'Option gamma 9' }, { id: 20, label: 'D', text: 'Option delta 9' }] },
    { question_id: 4, number: 3, text: 'Which queue structure suits multilevel feedback?', topic: 'CPU Scheduling', difficulty: 'easy', marks: 1.0,
      options: [{ id: 16, label: 'A', text: 'Option delta 7' }, { id: 13, label: 'B', text: 'Option alpha 7' }, { id: 15, label: 'C', text: 'Option gamma 7' }, { id: 14, label: 'D', text: 'Option beta 7' }] },
  ],
  answers: {},
}

export const attemptPractice = {
  ...attemptAssessment, session_id: 2, quiz_id: 2, quiz_title: 'Practice: SQL joins', kind: 'practice', confidence_enabled: true, can_check_answers: true,
}

export const checkResponse = { question_id: 3, correct_option_id: 10, is_correct: false, explanation: 'Beta 5 is correct because of reason 5.' }

export const resultBody = {
  session_id: 1, quiz_id: 1, quiz_title: 'Scheduling quiz 1', kind: 'assessment', attempt_no: 1, submitted_at: '2026-10-21T16:43:23.537314Z',
  submitted_by: 'student', is_late: true, feedback_available: true, feedback_message: null, raw_score: 2.0, max_score: 5.0, percentage: 40.0,
  late_penalty_pct: 10.0, final_percentage: 30.0, contribution_pct: 10.0, contribution_earned: 3.0, correct: 2, incorrect: 2, unanswered: 1,
  duration_s: 0.1, active_time_s: 80.0,
  items: [
    { question_id: 3, number: 1, text: 'Which scheduler is non-preemptive by default?', topic: 'CPU Scheduling', difficulty: 'hard', marks: 1.0,
      outcome: 'incorrect', confidence: 1, explanation: 'Beta 5 is correct because of reason 5.', math_verified: false, source_excerpt: null, time_spent_s: 20.0,
      options: [{ id: 11, label: 'A', text: 'Option gamma 5', is_correct: false, selected: true }, { id: 10, label: 'B', text: 'Option beta 5', is_correct: true, selected: false },
        { id: 9, label: 'C', text: 'Option alpha 5', is_correct: false, selected: false }, { id: 12, label: 'D', text: 'Option delta 5', is_correct: false, selected: false }] },
  ],
  topics: [{ topic_key: 't:1', topic: 'CPU Scheduling', correct: 2, incorrect: 2, skipped: 1, accuracy: 0.5, mastery_label: 'needs_improvement', mastery_score: 0.4528, next_difficulty: 'easy' }],
  recommendations: [{ id: 1, kind: 'practice_topic', topic: 'CPU Scheduling', subject: 'Operating Systems',
    reason: 'Practise CPU Scheduling because estimated mastery is 45% across 5 questions.', payload: { subject: 'Operating Systems', topic: 'CPU Scheduling', difficulty: 'easy', topic_id: 1 } }],
  can_retry: true,
}

export const topic = {
  topic_key: 't:1', subject: 'Operating Systems', topic: 'CPU Scheduling', topic_id: 1, status: 'weak', status_reason: 'Estimated mastery is 45% across 5 questions.',
  label: 'needs_improvement', label_text: 'Needs improvement', score: 0.4528, lower: 0.2218, upper: 0.6839, answers: 5, unique_questions: 5, correct: 2, incorrect: 2,
  skipped: 1, recent_accuracy: 0.5, historical_accuracy: null, next_difficulty: 'easy',
  explanation: 'Estimated mastery 45% (likely range 22–68%) from 5 answers on 5 questions: 2 correct, 2 wrong, 1 skipped.',
  last_activity: '2026-10-21T16:43:23.537314+00:00', score_100: 45, evidence_level: 'moderate', evidence_text: 'Limited evidence',
  trend: 'not_enough_data', trend_text: 'Not enough data for a trend', trend_reason: 'A trend needs at least 3 answered questions before the last 5 and 3 within them.',
  next_action: 'revise_concept', next_action_text: 'Revise the concept, then practise with easier questions.',
}

export const run = { run_id: 2, status: 'running', stage: 'Writing questions', ready: 2, total: 5, attempts: 3, rejected: {}, rejected_reasons: {}, error: null,
  quiz_id: 2, queue_position: 0, elapsed_s: 2.0, avg_question_s: null, grounded_on: null, difficulty_note: null }
