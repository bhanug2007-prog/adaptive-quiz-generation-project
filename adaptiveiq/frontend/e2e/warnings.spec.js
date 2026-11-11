// Disposable accounts and SQLite DB are provided by playwright.config.js.
import { test, expect } from '@playwright/test'

test.use({ permissions: ['microphone'], launchOptions: {
  ...(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {}),
  args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
} })

test('three warnings, duplicate upload, refresh, report and lecturer history preserve answers', async ({ page, playwright, browser }) => {
  test.setTimeout(180000)
  const headers = { 'X-Requested-With': 'AdaptiveIQ' }
  const lec = await playwright.request.newContext({ baseURL: 'http://localhost:5190', extraHTTPHeaders: headers })
  const stamp = Date.now()
  const post = async (api, url, data) => { const r = await api.post(url, { data, headers }); expect(r.ok(), await r.text()).toBeTruthy(); return r.json() }
  try {
    await post(lec, '/api/auth/register', { email: `warning-lec-${stamp}@example.com`, password: 'Passw0rd1', full_name: 'Warning Lecturer', role: 'lecturer', invite_code: 'dev-invite' })
    const course = await post(lec, '/api/lecturer/courses', { code: `W${stamp}`, title: 'Warning Test Course' })
    const subject = await post(lec, `/api/lecturer/courses/${course.id}/subjects`, { name: 'Operating Systems', quiz_weight_cap_pct: 20 })
    const unit = await post(lec, `/api/lecturer/subjects/${subject.id}/units`, { name: 'Scheduling' })
    const topic = await post(lec, `/api/lecturer/units/${unit.id}/topics`, { name: 'CPU Scheduling' })
    const run = await post(lec, '/api/lecturer/generate', { course_id: course.id, subject_id: subject.id, topic_id: topic.id, title: 'Warning Test Quiz', question_count: 3, difficulty: 'mixed' })
    let generated
    await expect.poll(async () => { generated = await (await lec.get(`/api/generation/${run.run_id}`)).json(); return generated.status }, { timeout: 90000 }).toBe('done')
    const qid = generated.quiz_id
    const quiz = await (await lec.get(`/api/lecturer/quizzes/${qid}`)).json()
    for (const item of quiz.items) await post(lec, `/api/lecturer/questions/${item.question.id}/review`, { action: 'approve' })
    expect((await lec.patch(`/api/lecturer/quizzes/${qid}`, { data: { contribution_pct: 5, monitor_tab: true, monitor_fullscreen: 'record', monitor_microphone: true } })).ok()).toBeTruthy()
    await post(lec, `/api/lecturer/quizzes/${qid}/publish`)
    await post(page.request, '/api/auth/register', { email: `warning-st-${stamp}@example.com`, password: 'Passw0rd1', full_name: 'Warning Student', role: 'student' })
    await post(page.request, '/api/student/courses/join', { join_code: course.join_code })
    const attempt = await post(page.request, `/api/student/quizzes/${qid}/start`, { monitoring_consent: true })
    const sid = attempt.session_id
    await page.goto(`/student/attempts/${sid}`)
    await page.getByRole('button', { name: 'Turn on monitoring and continue' }).click()
    await page.locator('.st-option').first().click()
    await expect(page.getByText('All answers saved')).toBeVisible()
    const answers = (await (await page.request.get(`/api/student/attempts/${sid}`)).json()).answers
    await expect.poll(() => page.evaluate(() => !!document.fullscreenElement)).toBe(true)
    await page.evaluate(() => document.exitFullscreen())
    await expect(page.locator('.st-activity-warning')).toContainText('Activity warning 1 of 3')
    await page.evaluate(() => window.dispatchEvent(new Event('blur')))
    await expect(page.locator('.st-activity-warning')).toContainText('Activity warning 2 of 3')
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    // Deterministic speech event injection; actual audio heuristic is covered by the focused detector tests.
    const speech = { seq: 100000, kind: 'activity_warning', at: new Date().toISOString(), duration_ms: 6000,
      details: { signal: 'speech', incident_id: 'e2e-speech-episode' } }
    const upload = `/api/student/attempts/${sid}/monitoring/events`
    await post(page.request, upload, { events: [speech] })
    const retry = await post(page.request, upload, { events: [speech] })
    expect(retry.duplicates).toBe(1)
    await page.evaluate(() => window.dispatchEvent(new Event('online')))
    await expect(page.locator('.st-activity-warning')).toContainText('Activity warning 3 of 3')
    await expect(page.locator('.st-activity-warning')).toContainText('Lecturer review required')
    await expect(page.locator('.st-option').first()).toBeEnabled()
    await page.screenshot({ path: 'test-results/activity-warning-third.png', fullPage: true })
    await page.reload()
    await expect(page.locator('.st-activity-warning')).toContainText('Activity warning 3 of 3')
    await page.getByRole('button', { name: 'Turn on monitoring and continue' }).click()
    await expect(page.getByText('Alerts: 3 / 3')).toBeVisible()
    const refreshed = await (await page.request.get(`/api/student/attempts/${sid}`)).json()
    expect(refreshed.status).toBe('in_progress')
    expect(refreshed.answers).toEqual(answers)
    await page.getByRole('button', { name: 'Report a false alert or device problem' }).click()
    await page.getByLabel('Related warning').selectOption('100000')
    await page.getByLabel('Details (optional)').fill('Background television, not my voice')
    await page.getByRole('button', { name: 'Send report' }).click()
    await expect(page.getByText(/Report saved for your lecturer/)).toBeVisible()
    const report = await (await lec.get(`/api/lecturer/quizzes/${qid}/monitoring`)).json()
    expect(report.students[0]).toMatchObject({ warning_count: 3, review_required: true, attempt_status: 'in_progress' })
    const lecturerContext = await browser.newContext({ storageState: await lec.storageState() })
    try {
      const lecturerPage = await lecturerContext.newPage()
      await lecturerPage.goto(`http://localhost:5190/lecturer/quizzes/${qid}`)
      await lecturerPage.getByRole('tab', { name: /Monitoring & activity/ }).click()
      await lecturerPage.getByRole('button', { name: /Timeline for Warning Student/ }).click()
      await expect(lecturerPage.getByRole('region', { name: 'Student warning history' })).toContainText('Activity warnings: 3 / 3')
      await expect(lecturerPage.getByText(/Student-reported false alert.*Background television/)).toBeVisible()
    } finally { await lecturerContext.close() }
  } finally { await lec.dispose() }
})
