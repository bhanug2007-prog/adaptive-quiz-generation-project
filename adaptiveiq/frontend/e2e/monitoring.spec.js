// Integrity monitoring in a real browser against a real backend. Chromium's fake camera (a moving test pattern,
// no face) and fake microphone are used, so the real MediaPipe face detector runs and should report "no face".
import { expect, test } from '@playwright/test'

const stamp = Date.now()
const lecturer = { name: 'Monitor Lecturer', email: `mlect${stamp}@example.com` }
const student = { name: 'Monitor Student', email: `mstud${stamp}@example.com` }
const PASSWORD = 'Passw0rd1'
const shared = {}

test.use({
  permissions: ['camera', 'microphone'],
  launchOptions: {
    ...(process.env.PLAYWRIGHT_CHROMIUM ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM } : {}),
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'],
  },
})

async function register(page, who, role) {
  await page.goto('/register')
  if (role === 'lecturer') await page.getByRole('radiogroup', { name: 'Account type' }).getByText('Lecturer').click()
  await page.getByLabel('Full name').fill(who.name)
  await page.getByLabel('Email').fill(who.email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByLabel('Confirm password').fill(PASSWORD)
  if (role === 'lecturer') await page.getByLabel('Lecturer invite code').fill('dev-invite')
  await page.getByRole('button', { name: 'Create account' }).click()
  await page.waitForURL(new RegExp(`/${role}`))
}

async function signIn(page, who) {
  await page.goto('/signin')
  await page.getByLabel('Email').fill(who.email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: /sign in/i }).click()
}

function watchErrors(page) {
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => {
    // MediaPipe's WebAssembly prints its own start-up notice on the error console; it is not an error.
    if (m.type() === 'error' && !/status of 4\d\d/.test(m.text()) && !/^INFO: Created TensorFlow Lite/.test(m.text())) errors.push(m.text())
  })
  return errors
}

test.describe.serial('Integrity monitoring', () => {
  test('lecturer turns monitoring on and publishes', async ({ page }) => {
    test.setTimeout(240_000)
    const errors = watchErrors(page)
    await register(page, lecturer, 'lecturer')
    const dlg = page.locator('dialog[open]')
    await page.goto('/lecturer/courses')
    await page.getByRole('button', { name: 'New course' }).click()
    await dlg.getByLabel('Course code').fill(`MON${stamp % 1000}`)
    await dlg.getByLabel('Title').fill('Monitored Course')
    await dlg.getByRole('button', { name: 'Create course' }).click()
    await page.waitForURL(/\/lecturer\/courses\/\d+/)
    const courseId = page.url().split('/').pop()
    shared.joinCode = (await page.locator('.lc-code--lg').textContent()).trim()
    await page.getByRole('button', { name: 'Add subject' }).first().click()
    await dlg.getByLabel('Subject name').fill('Operating Systems')
    await dlg.getByLabel(/Quiz weight cap/).fill('20')
    await dlg.getByRole('button', { name: 'Add subject' }).click()
    await page.getByLabel('Add unit').fill('Unit 1')
    await page.getByRole('button', { name: 'Add unit' }).click()
    await page.getByRole('button', { name: 'Add topic' }).click()
    await dlg.getByLabel('Topic name').fill('Deadlocks')
    await dlg.getByRole('button', { name: 'Add topic' }).click()

    await page.goto('/lecturer/create')
    await page.getByLabel('Course', { exact: true }).selectOption(courseId)
    await page.getByLabel('Quiz title').fill('Monitored quiz E2E')
    await page.getByLabel('Number of questions').fill('3')
    await page.getByRole('button', { name: 'Generate questions' }).click()
    await page.getByRole('button', { name: /Review \d+ questions/ }).click({ timeout: 150_000 })
    await page.waitForURL(/\/lecturer\/quizzes\/\d+/)
    shared.quizUrl = page.url().split('?')[0]
    shared.quizId = shared.quizUrl.split('/').pop()
    await expect(page.locator('article[aria-label="Question 1"]')).toBeVisible()
    for (let i = 0; i < 20; i++) {
      const approve = page.getByRole('button', { name: 'Approve', exact: true }).first()
      if (!(await approve.count())) break
      const remaining = await page.getByRole('button', { name: 'Approve', exact: true }).count()
      await approve.click()
      await expect(page.getByRole('button', { name: 'Approve', exact: true })).toHaveCount(remaining - 1)
    }
    await expect(page.getByRole('button', { name: 'Approve', exact: true })).toHaveCount(0)
    await page.getByRole('tab', { name: 'Settings' }).click()
    await page.getByLabel(/Contribution/).fill('5')
    await page.getByLabel('Record when students leave the quiz page').check()
    await page.getByLabel(/Camera: record when no face/).check()
    await page.getByLabel(/Microphone: record speech-like sound/).check()
    await page.getByLabel('Full screen').selectOption('record')
    await page.getByRole('button', { name: 'Save settings' }).click()
    await page.getByRole('tab', { name: 'Preview & publish', selected: true }).waitFor()
    await page.getByRole('button', { name: 'Publish to students' }).click()
    await dlg.getByRole('button', { name: 'Publish' }).click()
    await expect(page.getByText(/^Published /).first()).toBeVisible()
    expect(errors).toEqual([])
  })

  test('student agrees, the real face detector runs, and the record is shown', async ({ page }) => {
    test.setTimeout(180_000)
    const errors = watchErrors(page)
    // Observe native fake-device tracks so submission proves that capture is stopped.
    await page.addInitScript(() => {
      window.monitoringTestTracks = []
      const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices)
      navigator.mediaDevices.getUserMedia = async (constraints) => {
        const stream = await original(constraints)
        window.monitoringTestTracks.push(...stream.getTracks())
        return stream
      }
    })
    await register(page, student, 'student')
    await page.goto('/student/courses')
    await page.getByLabel('Join code').fill(shared.joinCode)
    await page.getByRole('button', { name: 'Join course' }).click()
    await expect(page.getByText(/You joined Monitored Course/)).toBeVisible()
    await page.goto('/student/assigned')
    await page.getByRole('link', { name: 'Monitored quiz E2E' }).first().click()
    await expect(page.getByText('This assessment is monitored')).toBeVisible()
    const start = page.getByRole('button', { name: /Start/ }).first()
    await expect(start).toBeDisabled()
    await page.getByLabel(/I have read what is recorded and agree/).check()
    await start.click()
    await page.waitForURL(/attempts\/\d+$/)
    await page.getByRole('button', { name: 'Turn on monitoring and continue' }).click()
    await page.locator('.st-option').first().waitFor()
    await expect(page.getByText('Camera on')).toBeVisible()
    await expect(page.getByText('Microphone on')).toBeVisible()
    await expect.poll(() => page.evaluate(() => !!document.fullscreenElement)).toBe(true)
    await page.evaluate(() => document.exitFullscreen())
    await expect(page.getByText('You left full screen. This was recorded for your lecturer.')).toBeVisible()
    // A controlled upload interruption tests the persistent batch and reconnect path.
    const endpoint = '**/monitoring/events*'
    await page.route(endpoint, (route) => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"test interruption"}' }))
    await page.evaluate(() => window.dispatchEvent(new Event('blur')))
    await page.evaluate(() => window.dispatchEvent(new Event('focus')))
    const sid = page.url().split('/').pop()
    await expect.poll(() => page.evaluate((id) => JSON.parse(sessionStorage.getItem(`aiq.monitor.${id}`)).pending.length, sid)).toBeGreaterThan(0)
    await page.unroute(endpoint)
    await page.evaluate(() => window.dispatchEvent(new Event('online')))
    await expect.poll(() => page.evaluate((id) => JSON.parse(sessionStorage.getItem(`aiq.monitor.${id}`)).pending.length, sid)).toBe(0)
    // The fake camera shows no face: after a few checks the student is told, and an event is recorded.
    await expect(page.getByText('The camera cannot see a face.')).toBeVisible({ timeout: 30_000 })
    await page.screenshot({ path: 'test-results/monitoring-student.png', fullPage: true })
    for (let i = 0; i < 3; i++) {
      await page.locator('.st-option').first().click()
      if (i < 2) await page.keyboard.press('ArrowRight')
    }
    await page.getByRole('button', { name: 'Submit quiz' }).click()
    await page.getByRole('button', { name: 'Submit now' }).click()
    await page.waitForURL(/result$/)
    expect(await page.evaluate(() => window.monitoringTestTracks.every((track) => track.readyState === 'ended'))).toBe(true)
    await expect(page.getByText('What was recorded during this attempt')).toBeVisible()
    await expect(page.getByText(/No face visible \(for \d+/).first()).toBeVisible()
    await expect(page.getByText(/Monitoring turned on \(camera allowed, microphone allowed\)/)).toBeVisible()
    const record = await page.request.get(`/api/student/attempts/${sid}/monitoring`)
    const saved = await record.json()
    expect(new Set(saved.events.map((e) => e.seq)).size).toBe(saved.events.length)
    expect(saved.events.map((e) => e.kind)).toEqual(expect.arrayContaining(['fullscreen_exit', 'page_hidden', 'page_visible']))
    // The intentional 503 is the only additional console error expected in this test.
    const unexpected = errors.filter((e) => !/status of 503/.test(e))
    expect(unexpected).toEqual([])
  })

  test('lecturer discovers and reviews Students A–E monitoring summary and timelines with neutral labels', async ({ page, playwright }) => {
    test.setTimeout(180_000)
    const errors = watchErrors(page)

    // Seed Students A..E via disposable test DB API to verify all signal & availability distinctions alongside Monitor Student.
    const iso = (offsetSec) => new Date(Date.now() + offsetSec * 1000).toISOString()
    async function seedStudent(name, email, { devices, events }) {
      const api = await playwright.request.newContext({
        baseURL: 'http://localhost:5190',
        extraHTTPHeaders: { 'X-Requested-With': 'AdaptiveIQ' },
      })
      try {
        const reg = await api.post('/api/auth/register', {
          data: { email, password: PASSWORD, full_name: name, role: 'student' },
        })
        expect(reg.status()).toBe(201)
        const join = await api.post('/api/student/courses/join', { data: { join_code: shared.joinCode } })
        expect(join.status()).toBe(200)
        const startRes = await api.post(`/api/student/quizzes/${shared.quizId}/start`, {
          data: { monitoring_consent: true },
        })
        expect(startRes.status()).toBe(200)
        const { session_id: sid } = await startRes.json()
        if (devices) {
          const devRes = await api.post(`/api/student/attempts/${sid}/monitoring/devices`, { data: devices })
          expect(devRes.status()).toBe(200)
        }
        if (events?.length) {
          const evRes = await api.post(`/api/student/attempts/${sid}/monitoring/events`, { data: { events } })
          expect(evRes.status()).toBe(200)
        }
        const subRes = await api.post(`/api/student/attempts/${sid}/submit`)
        expect(subRes.status()).toBe(200)
      } finally {
        await api.dispose()
      }
    }

    await seedStudent('Student A Tabs', `stua${stamp}@example.com`, {
      devices: { camera: 'granted', microphone: 'granted' },
      events: [
        { seq: 1, kind: 'monitoring_started', at: iso(-50), details: { camera: 'granted', microphone: 'granted' } },
        { seq: 2, kind: 'page_hidden', at: iso(-40), details: { reason: 'window_blur' } },
        { seq: 3, kind: 'page_visible', at: iso(-25), duration_ms: 15000, details: { reason: 'window_blur' } },
        { seq: 4, kind: 'page_hidden', at: iso(-20), details: { reason: 'tab_hidden' } },
        { seq: 5, kind: 'page_visible', at: iso(-8), duration_ms: 12000 },
      ],
    })
    await seedStudent('Student B Face', `stub${stamp}@example.com`, {
      devices: { camera: 'granted', microphone: 'granted' },
      events: [
        { seq: 1, kind: 'monitoring_started', at: iso(-50), details: { camera: 'granted', microphone: 'granted' } },
        { seq: 2, kind: 'face_none', at: iso(-30), duration_ms: 8000, details: { faces: 0 } },
        { seq: 3, kind: 'face_multiple', at: iso(-15), duration_ms: 3000, details: { faces: 2 } },
      ],
    })
    await seedStudent('Student C Audio', `stuc${stamp}@example.com`, {
      devices: { camera: 'granted', microphone: 'granted' },
      events: [
        { seq: 1, kind: 'monitoring_started', at: iso(-50), details: { camera: 'granted', microphone: 'granted' } },
        { seq: 2, kind: 'speech', at: iso(-22), duration_ms: 6000 },
      ],
    })
    await seedStudent('Student D Clean', `stud${stamp}@example.com`, {
      devices: { camera: 'granted', microphone: 'granted' },
      events: [
        { seq: 1, kind: 'monitoring_started', at: iso(-50), details: { camera: 'granted', microphone: 'granted' } },
      ],
    })
    await seedStudent('Student E Unavailable', `stue${stamp}@example.com`, {
      devices: null,
      events: [],
    })

    await signIn(page, lecturer)
    await page.waitForURL(/lecturer/)

    // Verify exact navigation path: Quizzes list -> Quiz detail banner -> Monitoring & activity
    await page.goto('/lecturer/quizzes')
    const quizRow = page.getByRole('row', { name: /Monitored quiz E2E/ })
    await expect(quizRow).toBeVisible()
    await expect(quizRow.getByRole('link', { name: 'Monitoring & activity' })).toBeVisible()
    await quizRow.getByRole('link', { name: 'Monitored quiz E2E' }).click()
    await expect(page.getByRole('region', { name: 'Monitoring and assessment activity' })).toBeVisible()
    await page.getByRole('button', { name: 'Open monitoring & activity' }).click()
    await expect(page.getByRole('heading', { name: 'Assessment monitoring & activity' })).toBeVisible()

    // Check Students A-E and Monitor Student distinctions
    const rowA = page.getByRole('row', { name: /Student A Tabs/ })
    const rowB = page.getByRole('row', { name: /Student B Face/ })
    const rowC = page.getByRole('row', { name: /Student C Audio/ })
    const rowD = page.getByRole('row', { name: /Student D Clean/ })
    const rowE = page.getByRole('row', { name: /Student E Unavailable/ })
    const rowMon = page.getByRole('row', { name: /Monitor Student/ })

    await expect(rowA.getByText('2 · 27 s')).toBeVisible()
    await expect(rowB.getByText('Needs review')).toBeVisible()
    await expect(rowB.getByText('1 · 8 s')).toBeVisible()
    await expect(rowC.getByText('Event recorded')).toBeVisible()
    await expect(rowC.getByText('1 · 6 s')).toBeVisible()
    await expect(rowD.getByText('Normal')).toBeVisible()
    await expect(rowE.getByText('Monitoring unavailable')).toBeVisible()
    await expect(rowE.getByText('Unavailable').first()).toBeVisible()
    await expect(rowE.getByText('Normal')).toHaveCount(0)
    await expect(rowMon.getByText(/Event recorded|Needs review/)).toBeVisible()

    // Capture full-page lecturer monitoring dashboard screenshot
    await page.screenshot({ path: 'test-results/monitoring-lecturer.png', fullPage: true })

    // Verify filter segments
    await page.getByRole('radio', { name: /No recorded events/ }).click()
    await expect(rowD).toBeVisible()
    await expect(rowE).toHaveCount(0)
    await page.getByRole('radio', { name: /Unavailable \/ not monitored/ }).click()
    await expect(rowE).toBeVisible()
    await expect(rowD).toHaveCount(0)
    await page.getByRole('radio', { name: /All students/ }).click()

    // Verify Student A timeline details + manual review persistence across reload
    await rowA.getByRole('button', { name: /Timeline/ }).click()
    const dlgA = page.locator('dialog[open]')
    await expect(dlgA.getByText('Quiz window lost focus')).toBeVisible()
    await expect(dlgA.getByText(/Source: Window focus monitor/).first()).toBeVisible()
    await expect(dlgA.getByText('Switched away from quiz tab')).toBeVisible()
    await expect(dlgA.getByText(/Duration: 15 s/)).toBeVisible()
    await expect(dlgA.getByText('Uploaded').first()).toBeVisible()
    await dlgA.getByLabel('Your note (optional, only you see it)').fill('Checked notification focus loss.')
    await dlgA.getByRole('button', { name: 'Mark: follow-up needed' }).click()
    await expect(dlgA.getByText('Reviewed — follow-up needed')).toBeVisible()
    await dlgA.getByRole('button', { name: 'Close' }).click()

    await page.reload()
    await expect(page.getByRole('row', { name: /Student A Tabs/ }).getByText('Reviewed — follow-up needed')).toBeVisible()
    await expect(page.getByRole('row', { name: /Student A Tabs/ }).getByText('Checked notification focus loss.')).toBeVisible()

    // Also review real browser Monitor Student attempt
    await page.getByRole('row', { name: /Monitor Student/ }).getByRole('button', { name: /Timeline/ }).click()
    const dlgMon = page.locator('dialog[open]')
    await expect(dlgMon.getByText(/No face visible/).first()).toBeVisible()
    await dlgMon.getByLabel('Your note (optional, only you see it)').fill('Fake-device verification only.')
    await dlgMon.getByRole('button', { name: 'Mark: no concern' }).click()
    await expect(dlgMon.getByText('Reviewed: no concern')).toBeVisible()
    await page.screenshot({ path: 'test-results/monitoring-timeline-dialog.png', fullPage: true })
    expect((await page.content()).toLowerCase()).not.toContain('cheat')
    expect(errors).toEqual([])
  })
})
