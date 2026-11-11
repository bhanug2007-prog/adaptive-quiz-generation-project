// Opt-in real Qwen/Groq verification. Requires the disposable live_quality_server on 8192
// and Vite on 5192. Never run this against the normal application's database.
import { chromium, request, expect } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'

const baseURL = 'http://localhost:5192'
const api = await request.newContext({ baseURL, extraHTTPHeaders: { 'X-Requested-With': 'AdaptiveIQ' } })
const email = `live-review-${Date.now()}@example.com`
const password = 'DisposableReview1!'
async function post(path, data) {
  const response = await api.post(path, { data })
  if (!response.ok()) throw new Error(`${path}: HTTP ${response.status()}`)
  return response.json()
}
mkdirSync('test-results', { recursive: true })
await post('/api/auth/register', { email, password, full_name: 'Disposable Review Tester', role: 'lecturer', invite_code: 'live-review-test' })
const course = await post('/api/lecturer/courses', { code: `LIVE${Date.now()}`, title: 'Disposable live Groq verification' })
const subject = await post(`/api/lecturer/courses/${course.id}/subjects`, { name: 'Operating Systems', quiz_weight_cap_pct: 20 })
const unit = await post(`/api/lecturer/subjects/${subject.id}/units`, { name: 'Processes' })
const topic = await post(`/api/lecturer/units/${unit.id}/topics`, { name: 'Process states' })
const created = await post('/api/lecturer/generate', {
  course_id: course.id, subject_id: subject.id, topic_id: topic.id, title: 'Live Groq review verification',
  question_count: 1, difficulty: 'easy',
  reference_text: 'A process is a program in execution. A running process is currently executing instructions on the CPU. A ready process can execute but is waiting to be assigned a CPU. A blocked process is waiting for an event such as input or output completion. The scheduler selects a ready process to run. The terminated state means the process has finished execution.',
})
console.log(JSON.stringify({ generation_started: created.run_id }))
let run
const deadline = Date.now() + 600_000
while (Date.now() < deadline) {
  run = await (await api.get(`/api/generation/${created.run_id}`)).json()
  if (!['queued', 'running'].includes(run.status)) break
  await new Promise((resolve) => setTimeout(resolve, 2000))
}
console.log(JSON.stringify({ generation_status: run.status, quality: run.quality }))
const quiz = await (await api.get(`/api/lecturer/quizzes/${run.quiz_id}`)).json()
const question = quiz.items?.[0]?.question
if (!question) throw new Error('The local model produced no stored question; inspect the disposable run.')
writeFileSync('test-results/live-quality-generated.json', JSON.stringify({ run, question }, null, 2))
expect(question.validation.quality.ai).toBeTruthy()
expect(question.validation.quality.ai_error).toBeNull()
expect(question.review_status).toBe('draft')
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM || 'C:/Program Files/Google/Chrome/Application/chrome.exe' })
try {
  const page = await browser.newPage()
  await page.goto(`${baseURL}/signin`)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForURL(/\/lecturer/)
  await page.goto(`${baseURL}/lecturer/quizzes/${run.quiz_id}`)
  const card = page.getByRole('article', { name: 'Question 1', exact: true })
  await expect(card.getByText(/AI review passed|AI review failed/).first()).toBeVisible()
  await card.getByText('Checks, source and model').click()
  await expect(card.getByText(new RegExp(`score ${Math.round(question.validation.quality.score)} / 100`))).toBeVisible()
  await page.screenshot({ path: 'test-results/live-quality-generated.png', fullPage: true })
  const before = await (await api.get(`/api/lecturer/questions/${question.id}/evaluations`)).json()
  const start = Date.now()
  const responsePromise = page.waitForResponse((r) => r.url().endsWith(`/questions/${question.id}/check-quality`) && r.request().method() === 'POST', { timeout: 100_000 })
  await card.getByRole('button', { name: 'Check again' }).click()
  const response = await responsePromise
  const checked = await response.json()
  const durationMs = Date.now() - start
  expect(response.status()).toBe(200)
  expect(checked.validation.quality.ai).toBeTruthy()
  expect(checked.validation.quality.ai_error).toBeNull()
  expect(checked.review_status).toBe('draft')
  await expect(card.getByText(new RegExp(`score ${Math.round(checked.validation.quality.score)} / 100`))).toBeVisible()
  const after = await (await api.get(`/api/lecturer/questions/${question.id}/evaluations`)).json()
  expect(after.length).toBe(before.length + 1)
  const persisted = await (await api.get(`/api/lecturer/questions/${question.id}`)).json()
  expect(persisted.validation.quality).toEqual(checked.validation.quality)
  await page.reload()
  await expect(page.getByText(/AI review passed|AI review failed/).first()).toBeVisible()
  await page.screenshot({ path: 'test-results/live-quality-rechecked.png', fullPage: true })
  writeFileSync('test-results/live-quality-verified.json', JSON.stringify({ httpStatus: response.status(), durationMs, checked, evaluations: after, persisted: true, browserRefreshed: true }, null, 2))
  console.log(JSON.stringify({ check_again_status: response.status(), latency_ms: durationMs, score: checked.validation.quality.score,
    verdict: checked.validation.quality.ai.correctness.verdict, difficulty: checked.validation.quality.assessed_difficulty,
    result: checked.validation.quality.status, audit_rows: after.length, browser_verified: true }))
} finally {
  await browser.close()
  await api.dispose()
}
