/** Every backend endpoint the frontend uses, in one place. See backend/app/api/* for the handlers. */
import { api, qs } from './client'

export const healthApi = {
  get: () => api.get('/api/health'),
}

export const authApi = {
  config: () => api.get('/api/auth/config'),
  me: () => api.get('/api/auth/me'),
  login: (email, password) => api.post('/api/auth/login', { email, password }),
  register: (body) => api.post('/api/auth/register', body),
  logout: () => api.post('/api/auth/logout'),
  updateMe: (body) => api.patch('/api/auth/me', body),
  changePassword: (current_password, new_password) => api.post('/api/auth/change-password', { current_password, new_password }),
  verifyEmail: (token) => api.post('/api/auth/verify-email', { token }),
  resendVerification: () => api.post('/api/auth/resend-verification'),
  forgotPassword: (email) => api.post('/api/auth/forgot-password', { email }),
  verifyResetToken: (token) => api.post('/api/auth/reset-password/verify', { token }),
  resetPassword: (token, new_password) => api.post('/api/auth/reset-password', { token, new_password }),
}

export const generationApi = {
  get: (runId) => api.get(`/api/generation/${runId}`),
  cancel: (runId) => api.post(`/api/generation/${runId}/cancel`),
  mine: () => api.get('/api/generation'),
}

export const topicsApi = {
  choices: () => api.get('/api/topics/search'),
}

export const documentsApi = {
  extract: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.upload('/api/documents/extract', form)
  },
  remove: (documentId) => api.del(`/api/documents/${documentId}`),
}

export const studentApi = {
  overview: () => api.get('/api/student/overview'),
  courses: () => api.get('/api/student/courses'),
  join: (join_code) => api.post('/api/student/courses/join', { join_code }),
  assigned: () => api.get('/api/student/quizzes/assigned'),
  practiceQuizzes: () => api.get('/api/student/quizzes/practice'),
  quiz: (id) => api.get(`/api/student/quizzes/${id}`),
  start: (quizId, body = {}) => api.post(`/api/student/quizzes/${quizId}/start`, body),
  attempt: (sid) => api.get(`/api/student/attempts/${sid}`),
  saveAnswer: (sid, qid, body) => api.put(`/api/student/attempts/${sid}/answers/${qid}`, body),
  checkAnswer: (sid, qid) => api.post(`/api/student/attempts/${sid}/answers/${qid}/check`),
  submit: (sid) => api.post(`/api/student/attempts/${sid}/submit`),
  result: (sid) => api.get(`/api/student/attempts/${sid}/result`),
  history: (kind) => api.get(`/api/student/history${qs({ kind })}`),
  generatePractice: (body) => api.post('/api/student/practice/generate', body),
  recommendedDifficulty: (p) => api.get(`/api/student/practice/recommended-difficulty${qs(p)}`),
  mastery: () => api.get('/api/student/mastery'),
  masteryHistory: (topic_key) => api.get(`/api/student/mastery/history${qs({ topic_key })}`),
  weakAreas: () => api.get('/api/student/weak-areas'),
  questionStatus: () => api.get('/api/student/question-status'),
  trends: () => api.get('/api/student/trends'),
  recommendations: () => api.get('/api/student/recommendations'),
  refreshRecommendations: () => api.post('/api/student/recommendations/refresh'),
  recommendationAction: (id, action) => api.post(`/api/student/recommendations/${id}/${action}`),
  revision: () => api.get('/api/student/revision'),
  startRevision: () => api.post('/api/student/revision/start'),
  confidence: () => api.get('/api/student/confidence'),
  studyPlan: () => api.get('/api/student/study-plan'),
  learningPlanPreview: (p) => api.get(`/api/student/learning-plan/preview${qs(p)}`),
  learningPlanCurrent: () => api.get('/api/student/learning-plan/current'),
  learningPlanCreate: (body = {}) => api.post('/api/student/learning-plan', body),
  learningPlanGet: (planId) => api.get(`/api/student/learning-plan/${planId}`),
  learningPlanApprove: (planId, body = {}) => api.post(`/api/student/learning-plan/${planId}/approve`, body),
  learningPlanDismiss: (planId, body = {}) => api.post(`/api/student/learning-plan/${planId}/dismiss`, body),
  learningPlanPostpone: (planId, body = {}) => api.post(`/api/student/learning-plan/${planId}/postpone`, body),
  learningPlanRefresh: (planId, body = {}) => api.post(`/api/student/learning-plan/${planId}/refresh`, body),
  monitoringDevices: (sid, body) => api.post(`/api/student/attempts/${sid}/monitoring/devices`, body),
  monitoringEvents: (sid, events) => api.post(`/api/student/attempts/${sid}/monitoring/events?warnings=true`, { events }),
  myMonitoring: (sid) => api.get(`/api/student/attempts/${sid}/monitoring`),
  monitoringReport: (sid, body) => api.post(`/api/student/attempts/${sid}/monitoring/reports`, body),
}

export const lecturerApi = {
  overview: (days = 30) => api.get(`/api/lecturer/overview${qs({ days })}`),
  // courses and hierarchy
  courses: () => api.get('/api/lecturer/courses'),
  createCourse: (body) => api.post('/api/lecturer/courses', body),
  course: (id) => api.get(`/api/lecturer/courses/${id}`),
  updateCourse: (id, body) => api.patch(`/api/lecturer/courses/${id}`, body),
  rotateJoinCode: (id) => api.post(`/api/lecturer/courses/${id}/join-code`),
  addSubject: (courseId, body) => api.post(`/api/lecturer/courses/${courseId}/subjects`, body),
  updateSubject: (id, body) => api.patch(`/api/lecturer/subjects/${id}`, body),
  deleteSubject: (id) => api.del(`/api/lecturer/subjects/${id}`),
  addUnit: (subjectId, body) => api.post(`/api/lecturer/subjects/${subjectId}/units`, body),
  updateUnit: (id, body) => api.patch(`/api/lecturer/units/${id}`, body),
  deleteUnit: (id) => api.del(`/api/lecturer/units/${id}`),
  addTopic: (unitId, body) => api.post(`/api/lecturer/units/${unitId}/topics`, body),
  updateTopic: (id, body) => api.patch(`/api/lecturer/topics/${id}`, body),
  deleteTopic: (id) => api.del(`/api/lecturer/topics/${id}`),
  addObjective: (topicId, body) => api.post(`/api/lecturer/topics/${topicId}/objectives`, body),
  deleteObjective: (id) => api.del(`/api/lecturer/objectives/${id}`),
  roster: (courseId) => api.get(`/api/lecturer/courses/${courseId}/roster`),
  enroll: (courseId, emails) => api.post(`/api/lecturer/courses/${courseId}/enroll`, { emails }),
  removeStudent: (courseId, studentId) => api.del(`/api/lecturer/courses/${courseId}/students/${studentId}`),
  // generation and question bank
  generate: (body) => api.post('/api/lecturer/generate', body),
  regenerate: (questionId, quizId) => api.post(`/api/lecturer/questions/${questionId}/regenerate${qs({ quiz_id: quizId })}`),
  questions: (p) => api.get(`/api/lecturer/questions${qs(p)}`),
  question: (id) => api.get(`/api/lecturer/questions/${id}`),
  createQuestion: (body) => api.post('/api/lecturer/questions', body),
  editQuestion: (id, body) => api.patch(`/api/lecturer/questions/${id}`, body),
  reviewQuestion: (id, action, note) => api.post(`/api/lecturer/questions/${id}/review`, { action, note }),
  duplicateQuestion: (id) => api.post(`/api/lecturer/questions/${id}/duplicate`),
  questionHistory: (id) => api.get(`/api/lecturer/questions/${id}/history`),
  checkQuality: (id) => api.post(`/api/lecturer/questions/${id}/check-quality`),
  questionEvaluations: (id) => api.get(`/api/lecturer/questions/${id}/evaluations`),
  deleteQuestion: (id) => api.del(`/api/lecturer/questions/${id}`),
  // quizzes
  quizzes: (p) => api.get(`/api/lecturer/quizzes${qs(p)}`),
  quiz: (id) => api.get(`/api/lecturer/quizzes/${id}`),
  createEmptyQuiz: (p) => api.post(`/api/lecturer/quizzes${qs(p)}`),
  updateQuiz: (id, body) => api.patch(`/api/lecturer/quizzes/${id}`, body),
  updateItems: (id, body) => api.post(`/api/lecturer/quizzes/${id}/items`, body),
  publish: (id) => api.post(`/api/lecturer/quizzes/${id}/publish`),
  unpublish: (id) => api.post(`/api/lecturer/quizzes/${id}/unpublish`),
  archive: (id) => api.post(`/api/lecturer/quizzes/${id}/archive`),
  releaseFeedback: (id) => api.post(`/api/lecturer/quizzes/${id}/release-feedback`),
  preview: (id) => api.get(`/api/lecturer/quizzes/${id}/preview`),
  deleteQuiz: (id) => api.del(`/api/lecturer/quizzes/${id}`),
  manualExport: (id) => api.text(`/api/lecturer/quizzes/${id}/export`),
  googleForm: (id) => api.post(`/api/lecturer/quizzes/${id}/google-form`),
  googleExports: (id) => api.get(`/api/lecturer/quizzes/${id}/google-form/exports`),
  // analytics
  courseAnalytics: (courseId, p) => api.get(`/api/lecturer/courses/${courseId}/analytics${qs(p)}`),
  heatmap: (courseId, p) => api.get(`/api/lecturer/courses/${courseId}/heatmap${qs(p)}`),
  heatmapCell: (courseId, student_id, topic_id) => api.get(`/api/lecturer/courses/${courseId}/heatmap/cell${qs({ student_id, topic_id })}`),
  quizQuestionAnalytics: (quizId) => api.get(`/api/lecturer/quizzes/${quizId}/question-analytics`),
  courseQuestionAnalytics: (courseId, flagged_only) => api.get(`/api/lecturer/courses/${courseId}/question-analytics${qs({ flagged_only })}`),
  insights: (courseId) => api.get(`/api/lecturer/courses/${courseId}/insights`),
  coverage: (courseId) => api.get(`/api/lecturer/courses/${courseId}/coverage`),
  // agents
  askClass: (body) => api.post('/api/lecturer/insights/ask', body),
  askHistory: (courseId) => api.get(`/api/lecturer/insights/history${qs({ course_id: courseId })}`),
  agentRun: (id) => api.get(`/api/lecturer/agent-runs/${id}`),
  generationAgent: (runId) => api.get(`/api/lecturer/generation/${runId}/agent`),
  // integrity monitoring
  quizMonitoring: (quizId) => api.get(`/api/lecturer/quizzes/${quizId}/monitoring`),
  monitoringTimeline: (id) => api.get(`/api/lecturer/monitoring/${id}`),
  monitoringReview: (id, body) => api.post(`/api/lecturer/monitoring/${id}/review`, body),
  modelQuality: () => api.get('/api/lecturer/model-quality'),
  students: (p) => api.get(`/api/lecturer/students${qs(p)}`),
  student: (id) => api.get(`/api/lecturer/students/${id}`),
  // reports (CSV downloads)
  downloadQuizResults: (id, name) => api.download(`/api/lecturer/reports/quizzes/${id}/results.csv`, name),
  downloadQuizCompletion: (id, name) => api.download(`/api/lecturer/reports/quizzes/${id}/completion.csv`, name),
  downloadQuizQuestions: (id, name) => api.download(`/api/lecturer/reports/quizzes/${id}/questions.csv`, name),
  downloadCourseMarks: (id, name) => api.download(`/api/lecturer/reports/courses/${id}/marks.csv`, name),
  downloadCourseTopics: (id, name) => api.download(`/api/lecturer/reports/courses/${id}/topics.csv`, name),
  // integrations
  googleStatus: () => api.get('/api/integrations/google/status'),
  googleConnect: () => api.get('/api/integrations/google/connect'),
  googleDisconnect: () => api.del('/api/integrations/google'),
}
